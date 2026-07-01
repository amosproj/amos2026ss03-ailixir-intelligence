import html
import json
import logging
import os
import re
import time
from typing import List
from xml.etree import ElementTree

import requests
from langchain.schema import Document

from src.backend.log.log import write_to_log
from src.backend.Scrapers.BaseScraper.base_scraper import BaseScraper
from src.backend.Scrapers.YouTube import INDEX_FILE_PATH, RAW_DIR_PATH
from src.backend.Types.you_tube import TypeYouTubeScrappingData
from src.backend.Utils.splitter import get_text_chunks


class YouTubeScraper(BaseScraper):
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('astrapy').setLevel(logging.WARNING)
    logging.getLogger('openai').setLevel(logging.WARNING)
    YOUTUBE_BASE_URL = (
        'https://www.youtube.com/youtubei/v1/player?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8'
    )
    INDEX = json.loads(open(INDEX_FILE_PATH).read())

    YOUTUBE_API_URL = 'https://www.googleapis.com/youtube/v3'

    @classmethod
    def api_get(cls, endpoint, params):
        api_key = os.getenv('YOUTUBE_DATA_API_V3')
        if not api_key:
            raise ValueError('YOUTUBE_DATA_API_V3 is missing or empty in .env')
        response = requests.get(
            f'{cls.YOUTUBE_API_URL}/{endpoint}',
            params={**params, 'key': api_key},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def __init__(self, element_id: str, domain='medical', sub_domain='nutrition'):
        super().__init__(element_id=element_id, domain=domain, sub_domain=sub_domain)

    @classmethod
    def index_file(cls) -> str:
        return INDEX_FILE_PATH

    @classmethod
    def base_dir(cls) -> str:
        return RAW_DIR_PATH

    def _get_video_data(self):
        payload = {
            'context': {'client': {'clientName': 'WEB', 'clientVersion': '2.20210721.00.00'}},
            'videoId': self.element_id,
        }
        headers = {'Content-Type': 'application/json'}
        for attempt, delay in enumerate((0, 2, 4, 8), start=1):
            if delay:
                time.sleep(delay)
            try:
                response = requests.post(
                    self.YOUTUBE_BASE_URL, headers=headers, json=payload, timeout=30
                )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                status = getattr(exc.response, 'status_code', None)
                if status not in (429, 500, 502, 503, 504) or attempt == 4:
                    raise

    def _get_captions(self, captions):
        for track in captions:
            if track['languageCode'] == 'en':
                track_url = track['baseUrl']
                res = requests.get(track_url, timeout=30)
                res.raise_for_status()
                return res.content
        return None

    def _parse_transcript(self, xml_content):
        root_xml = ElementTree.fromstring(xml_content)
        transcript = [element.text for element in root_xml.findall('.//text')]
        return html.unescape(' '.join(transcript))

    def get_documents(self, data: TypeYouTubeScrappingData) -> List[Document]:
        transcript = data.get('transcript', '')
        chunks = get_text_chunks(transcript)
        metadata = {
            **self._common_metadata(
                source='youtube',
                source_type='video',
                published_date='',
                document_keywords=data.get('keywords', []),
            ),
            'title': data.get('title', ''),
            'keywords': data.get('keywords', []),
            'viewCount': data.get('viewCount', 0),
            'author': data.get('author', ''),
            'ref': data.get('ref', ''),
            'content_section': data.get('transcriptSource', 'captions'),
        }
        documents = [Document(page_content=chunk, metadata=metadata) for chunk in chunks]
        return documents

    def _scrape(self) -> TypeYouTubeScrappingData:
        scrap_data: TypeYouTubeScrappingData = {}
        try:
            data = self._get_video_data()
            video_details = data['videoDetails']
            transcript = ''
            transcript_source = 'captions'
            captions = (
                data.get('captions', {})
                .get('playerCaptionsTracklistRenderer', {})
                .get('captionTracks', [])
            )
            xml_content = self._get_captions(captions)
            if xml_content:
                transcript = self._parse_transcript(xml_content)
            else:
                transcript = video_details.get('shortDescription', '')
                transcript_source = 'description'
            if not transcript.strip():
                return {}
            scrap_data['videoId'] = video_details.get('videoId', '')
            scrap_data['title'] = video_details.get('title', '')
            scrap_data['keywords'] = video_details.get('keywords', [])
            scrap_data['shortDescription'] = video_details.get('shortDescription', '')
            scrap_data['viewCount'] = int(video_details.get('viewCount', '0'))
            scrap_data['author'] = video_details.get('author', '')
            scrap_data['transcript'] = re.sub(r'\n+', ' ', transcript)
            scrap_data['transcriptSource'] = transcript_source
            scrap_data['ref'] = f'https://www.youtube.com/watch?v={scrap_data["videoId"]}'
            return scrap_data
        except Exception as e:
            # print(f'Error: {e} No caption found for videoId: {self.element_id}')
            error_msg = f'Error: {e} No caption found for videoId: {self.element_id}'
            write_to_log(self.element_id, self.__class__.__name__, error_msg)
            return {}

    @classmethod
    def get_all_video_ids(cls, channel_id: str, limit=None) -> list[str]:
        channel = cls.api_get(
            'channels', {'part': 'contentDetails', 'id': channel_id}
        )
        items = channel.get('items', [])
        if not items:
            return []
        uploads_id = items[0]['contentDetails']['relatedPlaylists']['uploads']

        all_video_ids = []
        npt = None
        while True:
            page_size = min(50, limit - len(all_video_ids)) if limit else 50
            if page_size <= 0:
                break
            params = {
                'part': 'contentDetails',
                'playlistId': uploads_id,
                'maxResults': page_size,
            }
            if npt:
                params['pageToken'] = npt
            res = cls.api_get(
                'playlistItems',
                params,
            )
            video_ids = [
                item['contentDetails']['videoId'] for item in res.get('items', [])
            ]
            all_video_ids.extend(video_ids)
            if limit and len(all_video_ids) >= limit:
                break
            npt = res.get('nextPageToken', None)
            if not npt:
                break
        return all_video_ids

    @classmethod
    def _find_channel_id(cls, handle: str | None, user: str | None) -> str:
        params = {'part': 'id'}
        if handle:
            params['forHandle'] = handle.lstrip('@')
        if user:
            params['forUsername'] = user
        res = cls.api_get('channels', params)
        if 'items' in res and len(res['items']) > 0:
            channel_id = res['items'][0]['id']
            return channel_id
        return None

    @classmethod
    def get_channel_id(cls, url: str) -> str:
        channel_id = ''
        if url in cls.INDEX['channel_map']:
            channel_id = cls.INDEX['channel_map'][url]
        else:
            if '/channel/' in url:
                channel_id = url.strip().split('/')[-1]
            elif '/user/' in url:
                user = url.strip().split('/')[-1]
                channel_id = cls._find_channel_id(user=user, handle=None)
            else:
                handle = url.strip().split('/')[-1]
                channel_id = cls._find_channel_id(handle=handle, user=None)
        cls.INDEX['channel_map'][url] = channel_id
        with open(INDEX_FILE_PATH, 'w') as f:
            f.write(json.dumps(cls.INDEX, indent=2))
        return channel_id

    @classmethod
    def get_all_possible_elements(cls, target) -> List[BaseScraper]:
        old_indexes = set(cls.INDEX['indexes'])
        channel_id = cls.get_channel_id(url=target.url)
        candidate_indexes = cls.get_all_video_ids(
            channel_id=channel_id, limit=target.limit
        )
        new_target_elements = [id for id in candidate_indexes if id not in old_indexes]
        if target.limit is not None:
            new_target_elements = new_target_elements[: target.limit]
        return [
            YouTubeScraper(element_id=id, domain=target.domain, sub_domain=target.sub_domain)
            for id in new_target_elements
        ]
