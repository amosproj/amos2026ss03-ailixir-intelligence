import hashlib
import json
import os
import re
import time
from abc import ABCMeta, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional

from langchain_core.documents import Document
from langchain_astradb import AstraDBVectorStore
from langchain_openai import OpenAIEmbeddings

from src.backend.log.log import write_to_log
from src.backend.Types.base_type import TypeBaseScrappingData


def record_scrape_status(source: str, element_id: str, status: str, reason: str = ''):
    status_file_path = os.path.join('data', 'log', 'scrape_status.jsonl')
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'source': source,
        'element_id': str(element_id),
        'status': status,
        'reason': reason,
    }
    os.makedirs(os.path.dirname(status_file_path), exist_ok=True)
    with open(status_file_path, 'a', encoding='utf-8') as file:
        file.write(json.dumps(entry) + '\n')


class BaseScraper(metaclass=ABCMeta):
    DEFAULT_DOMAIN = 'medical'
    PAPER_REGISTRY_PATH = os.path.join('data', 'papers', 'index.json')

    def __init__(
        self,
        element_id: str,
        domain: str = DEFAULT_DOMAIN,
        sub_domain: str = 'nutrition',
        category: str = '',
    ):
        self.element_id = element_id
        self.domain = domain
        self.sub_domain = sub_domain
        self.category = category

    def __repr__(self):
        return 'Scraper(' + str(self.element_id) + ')'

    @classmethod
    @abstractmethod
    def index_file(cls) -> str:
        pass

    @classmethod
    @abstractmethod
    def base_dir(cls) -> str:
        pass

    @abstractmethod
    def _scrape(self) -> str:
        pass

    @classmethod
    @abstractmethod
    def get_all_possible_elements(cls, target) -> []:
        pass

    @abstractmethod
    def get_documents(self, data: TypeBaseScrappingData) -> List[Document]:
        pass

    def is_scrapped(self) -> bool:
        with open(self.index_file(), encoding='utf-8') as index_file:
            indexes: List[str] = json.load(index_file).get('indexes', [])
        return str(self.element_id) in {str(index) for index in indexes}

    def _save(self, scrapped_dict: dict):
        file_path = os.path.join(self.base_dir(), f'{self.element_id}.json')
        with open(file_path, 'w') as file:
            json.dump(scrapped_dict, file, indent=2)

    def _save_vector_docs(self, documents: List[Document]):
        if not documents:
            raise ValueError('No text chunks were produced for embedding')
        vector_store = AstraDBVectorStore(
            embedding=OpenAIEmbeddings(
                model='text-embedding-3-small',
                openai_api_key=os.getenv('OPEN_AI_API'),
            ),
            api_endpoint=os.getenv('ASTRA_DB_API_ENDPOINT'),
            token=os.getenv('ASTRA_DB_TOKEN'),
            namespace=os.getenv('ASTRA_DB_NAMESPACE'),
            collection_name=os.getenv('ASTRA_DB_COLLECTION'),
        )
        delays = (0, 2, 4, 8)
        document_ids = [
            hashlib.sha256(
                f'{self.__class__.__name__}:{self.element_id}:{index}'.encode('utf-8')
            ).hexdigest()
            for index, _ in enumerate(documents)
        ]
        for index, document in enumerate(documents):
            document.metadata.setdefault('source_id', str(self.element_id))
            document.metadata.setdefault('chunk_index', index)
        for attempt, delay in enumerate(delays, start=1):
            if delay:
                time.sleep(delay)
            try:
                # Stable IDs make this an upsert in AstraDB instead of creating
                # duplicate vectors if a local index is lost or a run is retried.
                vector_store.add_documents(documents=documents, ids=document_ids)
                return
            except Exception as exc:
                message = str(exc).lower()
                # Astra's gateway (openresty) intermittently returns transient
                # 400/502 HTML errors while the serverless DB is under load or
                # waking, and these clear on retry. 400 is included deliberately:
                # a genuine bad request will not recover, but in that case we
                # simply exhaust the retries and raise, exactly as before.
                retryable = any(
                    marker in message
                    for marker in ('400', '429', '500', '502', '503', '504', 'timeout')
                )
                if not retryable or attempt == len(delays):
                    raise

    def record_status(self, status: str, reason: str = ''):
        record_scrape_status(
            self.__class__.__name__, self.element_id, status, reason
        )

    def _paper_keys(self, data: dict) -> List[str]:
        """Return cross-source keys for scholarly papers, strongest key first."""
        if self.__class__.__name__ not in {'ArchiveScraper', 'PubMedScraper'}:
            return []

        keys = []
        doi = str(data.get('doi') or data.get('ref') or '').strip().lower()
        if 'doi.org/' in doi:
            doi = doi.split('doi.org/', 1)[1]
        if doi.startswith('doi:'):
            doi = doi[4:]
        doi = doi.split('?', 1)[0].strip().rstrip('.,;')
        if doi.startswith('10.') and '/' in doi:
            keys.append(f'doi:{doi}')

        title = re.sub(r'[^a-z0-9]+', ' ', str(data.get('title', '')).lower()).strip()
        if len(title) >= 20:
            keys.append(f'title:{hashlib.sha256(title.encode("utf-8")).hexdigest()}')
        return keys

    def _paper_duplicate(self, data: dict):
        keys = self._paper_keys(data)
        if not keys or not os.path.exists(self.PAPER_REGISTRY_PATH):
            return None
        with open(self.PAPER_REGISTRY_PATH, encoding='utf-8') as registry_file:
            papers = json.load(registry_file).get('papers', {})
        return next((papers[key] for key in keys if key in papers), None)

    def _register_paper(self, data: dict):
        keys = self._paper_keys(data)
        if not keys:
            return
        os.makedirs(os.path.dirname(self.PAPER_REGISTRY_PATH), exist_ok=True)
        registry = {'papers': {}}
        if os.path.exists(self.PAPER_REGISTRY_PATH):
            with open(self.PAPER_REGISTRY_PATH, encoding='utf-8') as registry_file:
                registry = json.load(registry_file)
        record = {
            'source': self.__class__.__name__,
            'element_id': str(self.element_id),
            'title': str(data.get('title', '')),
            'doi': str(data.get('doi') or data.get('ref') or ''),
        }
        papers = registry.setdefault('papers', {})
        for key in keys:
            papers[key] = record
        with open(self.PAPER_REGISTRY_PATH, 'w', encoding='utf-8') as registry_file:
            json.dump(registry, registry_file, indent=2, sort_keys=True)

    def _mark_as_scrapped(self):
        with open(type(self).index_file(), 'r+', encoding='utf-8') as file:
            index_data = json.load(file)
            indexes = index_data.get('indexes', [])
            if str(self.element_id) not in {str(index) for index in indexes}:
                indexes.append(self.element_id)
            index_data['indexes'] = indexes
            file.seek(0)
            json.dump(index_data, file, indent=2)
            file.truncate()

    def _common_metadata(
        self,
        source: str,
        source_type: str,
        published_date: str = '',
        domain: Optional[str] = None,
        sub_domain: Optional[str] = None,
        category: Optional[str] = None,
        query_keywords: Optional[List[str]] = None,
        document_keywords: Optional[List[str]] = None,
    ) -> dict:
        return {
            'domain': domain or self.domain,
            'sub_domain': sub_domain or self.sub_domain,
            'category': category or self.category,
            'query_keywords': query_keywords or [],
            'document_keywords': document_keywords or [],
            'source': source,
            'source_type': source_type,
            'published_date': str(published_date or ''),
            'ingested_at': datetime.now(timezone.utc).isoformat(),
        }

    def scrape_and_save(self):
        # Enforce the index at the final boundary as well as during discovery.
        # This protects against duplicate targets in one config and direct calls.
        if self.is_scrapped():
            print(f'Skipping already processed element {self.element_id}')
            self.record_status('skipped', 'Already present in source index')
            return

        scrapped_dict = self._scrape()
        # Check if the scrapped_dict is empty
        if not scrapped_dict:
            print(f'No data found for {self.element_id}')
            write_to_log(
                self.element_id, self.__class__.__name__, f'No data found for {self.element_id}'
            )
            self.record_status('skipped', 'No usable source content')
            return
        duplicate = self._paper_duplicate(scrapped_dict)
        if duplicate:
            reason = (
                f'Paper already ingested by {duplicate["source"]} '
                f'({duplicate["element_id"]})'
            )
            print(f'Skipping {self.element_id}: {reason}')
            self._mark_as_scrapped()
            self.record_status('skipped', reason)
            return
        # save scrapped json file
        self._save(scrapped_dict)
        # create chunk documents
        documents = self.get_documents(scrapped_dict)
        # Save the vector documents
        self._save_vector_docs(documents)
        # Update the indexes
        self._mark_as_scrapped()
        self._register_paper(scrapped_dict)
        self.record_status('success')
