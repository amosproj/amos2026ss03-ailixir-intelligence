import json
import os
from typing import List

import arxiv
import requests
from langchain_core.documents import Document
from pypdf import PdfReader

from src.backend.log.log import write_to_log
from src.backend.Scrapers.Archive import INDEX_FILE_PATH, RAW_DIR_PATH
from src.backend.Scrapers.BaseScraper.base_scraper import BaseScraper
from src.backend.Types.archive import TypeArchiveScrappingData
from src.backend.Utils.splitter import get_text_chunks


class ArchiveScraper(BaseScraper):
    INDEX = json.loads(open(INDEX_FILE_PATH).read())

    def __init__(
        self,
        element_id: str,
        query_keywords=None,
        domain='medical',
        sub_domain='nutrition',
        category='',
    ):
        super().__init__(
            element_id=element_id, domain=domain, sub_domain=sub_domain, category=category
        )
        self.query_keywords = query_keywords or []

    @classmethod
    def index_file(cls) -> str:
        return INDEX_FILE_PATH

    @classmethod
    def base_dir(cls) -> str:
        return RAW_DIR_PATH

    # ---------------------------------------------------------
    # MARK: arXiv Queries
    # ---------------------------------------------------------

    @classmethod
    def extract_arxiv_id_from_url(cls, url):
        return url.split('/')[-1]

    @classmethod
    def query_ids(
        cls, keywords, max_results, query_mode='and', since_date=None
    ) -> list[str]:
        if query_mode == 'raw':
            query = ' '.join(keywords)
        else:
            operator = ' AND ' if query_mode == 'and' else ' OR '
            query = operator.join(f'all:{keyword}' for keyword in keywords)
        if since_date:
            compact_date = since_date.replace('-', '')
            query = f'({query}) AND submittedDate:[{compact_date}0000 TO 300012312359]'
        return [
            cls.extract_arxiv_id_from_url(url)
            for url in cls.search_arxiv_ids(query, max_results)
        ]

    @classmethod
    def search_arxiv_ids(cls, query, max_results) -> list[str]:
        """Search ArXiv for articles related to a query and return the ids."""
        client = arxiv.Client()
        search = arxiv.Search(
            query=query, max_results=max_results, sort_by=arxiv.SortCriterion.SubmittedDate
        )
        return [result.entry_id for result in client.results(search)]

    def get_paper_from_arxiv_id(self, id):
        """Get paper object from an arxiv id (example id: 2405.10746v1)."""
        search = arxiv.Search(id_list=[id])
        client = arxiv.Client()
        results = list(client.results(search))
        if results:
            return results[0]
        else:
            return None

    # ---------------------------------------------------------
    # MARK: Metadata Scraping
    # ---------------------------------------------------------

    def get_title_from_paper(self, paper):
        try:
            return paper.title
        except AttributeError:
            raise ValueError('No title found for paper.')

    def get_authors_from_paper(self, paper):
        try:
            return ', '.join([author.name for author in paper.authors])
        except AttributeError:
            raise ValueError('No authors found for paper.')

    def get_abstract_from_paper(self, paper):
        try:
            return paper.summary
        except AttributeError:
            raise ValueError('No abstract found for paper.')

    def get_publication_date_from_paper(self, paper):
        try:
            return paper.published
        except AttributeError:
            raise ValueError('No publication date found for paper.')

    def get_pdf_url_from_paper(self, paper):
        try:
            return paper.pdf_url
        except AttributeError:
            raise ValueError('No PDF URL found for paper.')

    def get_doi_from_paper(self, paper):
        return str(getattr(paper, 'doi', '') or '')

    def get_keywords_from_paper(self, paper):
        keywords = []
        try:
            keywords.extend(getattr(paper, 'categories', []) or [])
        except AttributeError:
            pass
        try:
            primary_category = getattr(paper, 'primary_category', '')
            if primary_category:
                keywords.append(primary_category)
        except AttributeError:
            pass
        return sorted(set(keywords))

    # ---------------------------------------------------------
    # MARK: Text Scraping
    # ---------------------------------------------------------

    def get_paper_pdf(self, paper, pdf_url, title=None, path='papers/'):
        """Download the PDF of a paper and save it to a specified directory."""
        if title is None:
            title = pdf_url.split('/')[-1]  # DOI

        if not os.path.exists(path):
            os.makedirs(path)

        filename = ''.join(
            character if character not in '<>:"/\\|?*' else '_'
            for character in str(title)
        ).strip()

        # arxiv 4 removed Result.download_pdf(); download its canonical PDF URL.
        response = requests.get(pdf_url, timeout=120)
        response.raise_for_status()
        with open(os.path.join(path, filename + '.pdf'), 'wb') as pdf_file:
            pdf_file.write(response.content)
        return filename

    def get_txt_from_pdf(
        self, filename: str, path='papers/', create_txt_file=False, keep_pdfs=False
    ):
        """Extract text from a PDF file using the PyMuPDF library."""
        filepath = path + f'{filename}.pdf'
        reader = PdfReader(filepath)
        text = ''
        for page in reader.pages:
            text = text + page.extract_text()

        # Delete symbols that cannot be encoded using UTF-8
        text = text.encode('utf-8', 'ignore').decode('utf-8')

        if create_txt_file:
            f = open(filename + '.txt', 'a', encoding='utf-8')
            f.write(text)
            f.close()

        if keep_pdfs is not True:
            if os.path.exists(filepath):
                os.remove(filepath)

        return text

    # ---------------------------------------------------------
    # MARK: _scrape & get_ids
    # ---------------------------------------------------------

    def get_documents(self, data: TypeArchiveScrappingData) -> List[Document]:
        transcript = data.get('transcript', '')
        chunks = get_text_chunks(transcript)
        metadata = {
            **self._common_metadata(
                source='archive',
                source_type='paper',
                published_date=data.get('publicationDate', ''),
                query_keywords=self.query_keywords,
                document_keywords=data.get('documentKeywords', []),
            ),
            'abstract': data.get('abstract', ''),
            'authors': data.get('authors', ''),
            'publicationDate': data.get('publicationDate', ''),
            'title': data.get('title', ''),
            'ref': data.get('ref', ''),
            'doi': data.get('doi', ''),
        }
        documents = [Document(page_content=chunk, metadata=metadata) for chunk in chunks]
        return documents

    def _scrape(self) -> TypeArchiveScrappingData:
        try:
            paper = getattr(self, '_discovered_paper', None) or self.get_paper_from_arxiv_id(
                self.element_id
            )
            if paper is None:
                write_to_log(
                    self.element_id, self.__class__.__name__,
                    f'Paper does not exist for id: {self.element_id}',
                )
                return {}

            title = self.get_title_from_paper(paper)
            abstract = self.get_abstract_from_paper(paper)
            pdf_url = self.get_pdf_url_from_paper(paper)

            # Full text is best-effort: arXiv PDFs occasionally 404/time out or
            # fail to parse. The abstract always comes from the API, so fall back
            # to it (then the title) rather than dropping the paper entirely.
            text = ''
            try:
                file_name = self.get_paper_pdf(paper, pdf_url, title)
                text = self.get_txt_from_pdf(file_name)
            except Exception as exc:
                write_to_log(
                    self.element_id, self.__class__.__name__,
                    f'PDF unavailable, embedding abstract instead: {exc}',
                )
            text = (text or '').strip() or abstract.strip() or title.strip()

            return {
                'abstract': abstract,
                'authors': self.get_authors_from_paper(paper),
                'documentKeywords': self.get_keywords_from_paper(paper),
                'ref': pdf_url,
                'doi': self.get_doi_from_paper(paper),
                'publicationDate': str(self.get_publication_date_from_paper(paper)),
                'title': title,
                'transcript': text,
            }

        except Exception as e:
            write_to_log(self.element_id, self.__class__.__name__, f'Failed due to {e}')
            print(e)
            return {}

    @classmethod
    def get_all_possible_elements(cls, target) -> List[BaseScraper]:
        with open(cls.index_file(), encoding='utf-8') as file:
            old_indexes = set(json.load(file).get('indexes', []))
        new_indexes = set(
            cls.query_ids(
                target.keywords,
                target.max_results,
                target.query_mode,
                target.since_date,
            )
        )
        new_target_elements = new_indexes - old_indexes
        candidates = [
            ArchiveScraper(
                element_id=id,
                query_keywords=target.keywords,
                domain=target.domain,
                sub_domain=target.sub_domain,
                category=target.category,
            )
            for id in new_target_elements
        ]
        accepted = []
        for candidate in candidates:
            try:
                paper = candidate.get_paper_from_arxiv_id(candidate.element_id)
                identity = {
                    'title': candidate.get_title_from_paper(paper),
                    'doi': candidate.get_doi_from_paper(paper),
                }
                duplicate = candidate._paper_duplicate(identity)
                if duplicate:
                    reason = (
                        f'Paper already ingested by {duplicate["source"]} '
                        f'({duplicate["element_id"]})'
                    )
                    candidate._mark_as_scrapped()
                    candidate.record_status('skipped', reason)
                    continue
                candidate._discovered_paper = paper
            except Exception:
                # Let the normal scrape path report detailed source errors.
                pass
            accepted.append(candidate)
        return accepted
