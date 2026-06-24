import logging
import os
from typing import List

from langchain_core.documents import Document

from . import INDEX_FILE_PATH, PAPERS_DIR, RAW_DIR_PATH, ledger
from .base_scraper import BaseScraper
from .log import write_to_log
from .splitter import get_text_chunks
from .types import TypePubMedScrappingData

logging.getLogger('paperscraper').setLevel(logging.ERROR)  # suppress warnings

from Bio import Entrez  # noqa: E402
from paperscraper.pdf import save_pdf  # noqa: E402
from pypdf import PdfReader  # noqa: E402

# NCBI asks callers to identify themselves; an API key raises the rate limit.
ENTREZ_EMAIL = os.getenv('NCBI_ENTREZ_EMAIL', 'email@example.com')
ENTREZ_API_KEY = os.getenv('NCBI_API_KEY')


def _configure_entrez():
    Entrez.email = ENTREZ_EMAIL
    if ENTREZ_API_KEY:
        Entrez.api_key = ENTREZ_API_KEY


class PubMedScraper(BaseScraper):
    def __init__(self, element_id: str, disease: str | None = None):
        super().__init__(element_id=element_id)
        self.disease = disease

    @classmethod
    def index_file(cls) -> str:
        return INDEX_FILE_PATH

    @classmethod
    def base_dir(cls) -> str:
        return RAW_DIR_PATH

    # ---------------------------------------------------------
    # MARK: Pubmed Queries
    # ---------------------------------------------------------

    """Get Pubmed ID's for a search query (eg. 'nutrition cancer').

  only retrieves free full text papers (filter)
  can only retrieve the first 10k search results so be specific with search terms"""

    @classmethod
    def search_free_fulltext(cls, query: str, max_results=10_000):
        _configure_entrez()
        handle = Entrez.esearch(
            db='pubmed',
            sort='relevance',
            retmax=max_results,
            retmode='xml',
            term=query + ' AND free full text[sb]',
        )
        # optionally: could further filter with mindate and maxdate args,
        # see docs: https://www.ncbi.nlm.nih.gov/books/NBK25499/
        results = Entrez.read(handle)
        handle.close()
        return results['IdList']

    """Get metadata for one pubmed id, received from search query.

  Metadata is stored in a dictionary"""

    def fetch_details(self, id):
        _configure_entrez()
        handle = Entrez.efetch(db='pubmed', retmode='xml', id=id)
        results = Entrez.read(handle)
        handle.close()
        return results

    # MARK: Metadata

    """Retrieve doi url from details dictionary received from fetch_details() method."""

    def get_doi_from_details(self, details_dict):
        try:
            id_list = details_dict['PubmedArticle'][0]['PubmedData']['ArticleIdList']
            doi = ''
            for entry in id_list:
                attr = entry.attributes.get('IdType')
                if attr == 'doi':
                    doi = f'https://doi.org/{entry}'
            return doi
            # return doi
        except Exception as e:
            print('Error: pubmed_scraping: get_doi_from_pubmed_id: Could not retrieve doi.')
            print(e)
            return ''

    """Retrieve abstract from details dictionary received from fetch_details() method."""

    def get_abstract_from_details(self, details_dict):
        try:
            # Maybe check why 'AbstractText' is a list of texts with only 1 entry
            # (in all examples seen)
            abstract = details_dict['PubmedArticle'][0]['MedlineCitation']['Article']
            abstract = abstract['Abstract']['AbstractText'][0]
            return str(abstract)
        except Exception as e:
            print(
                'Error: pubmed_scraping: get_abstract_from_details:'
                + ' Could not retrieve abstract.'
            )
            print(e)
            return ''

    """Retrieve title from details dictionary received from fetch_details() method."""

    def get_title_from_details(self, details_dict):
        try:
            title = details_dict['PubmedArticle'][0]['MedlineCitation']['Article']
            title = title['ArticleTitle']
            if title.endswith('.'):
                title = title[:-1]
            return title
        except Exception as e:
            print('Error: pubmed_scraping: get_title_from_details: Could not retrieve title.')
            print(e)
            return ''

    """Retrieve authors str from details dictionary received from fetch_details() method.

  the authors are separated by ', ' delimeter"""

    def get_authors_from_details(self, details_dict):
        try:
            author_dict_list = details_dict['PubmedArticle'][0]['MedlineCitation']['Article']
            author_dict_list = author_dict_list['AuthorList']
            author_strings = []
            for entry in author_dict_list:
                author = entry['ForeName'] + ' ' + entry['LastName']
                author_strings.append(author)
            return ', '.join(author_strings)
        except Exception as e:
            print(
                'Error: pubmed_scraping: get_authors_from_details:' + ' Could not retrieve authors.'
            )
            print(e)
            return ''

    """Retrieve publication date from details dict received from fetch_details() method."""

    def get_publication_date_from_details(self, details_dict):
        try:
            date_dict = details_dict['PubmedArticle'][0]['MedlineCitation']['Article']
            date_dict = date_dict['Journal']['JournalIssue']['PubDate']
            # sometimes date parts are incomplete to we scrape separately
            date = ''
            try:
                day = date_dict['Day']
                date += str(day) + ' '
            except Exception:
                pass
            try:
                month = date_dict['Month']
                date += str(month) + ' '
            except Exception:
                pass
            try:
                year = date_dict['Year']
                date += str(year)
            except Exception:
                pass
            return date
        except Exception as e:
            print(
                'Error: pubmed_scraping: get_publication_date_from_details:'
                + 'Could not retrieve date.'
            )
            print(e)
            return ''

    # ---------------------------------------------------------
    # MARK: Get pdf and text
    # ---------------------------------------------------------

    def get_paper_from_doi(self, doi: str, title=None, path=PAPERS_DIR):
        # potentially add title and then pdf files can be stored under the title
        # instead of their doi (as filename)
        # if the title is given, it will be used. Otherwise the file will be saved
        # under its DOI
        if title is None:
            title = doi
        if not os.path.exists(path):
            os.makedirs(path)

        paper_data = {'doi': doi}
        filename = f'{title}'.replace('/', '').replace('?', '').replace('!', '')
        filepath = os.path.join(path, filename)

        save_pdf(paper_data, filepath=filepath + '.pdf')
        return filename

    def get_txt_from_pdf(self, filename: str, path=PAPERS_DIR, create_txt_file=False, keep_pdfs=False):
        text = ''
        try:
            filepath = os.path.join(path, f'{filename}.pdf')
            reader = PdfReader(filepath)
            for page in reader.pages:
                text = text + page.extract_text()

            if create_txt_file:
                f = open(filename + '.txt', 'a', encoding='utf-8')
                f.write(text)
                f.close()

            if keep_pdfs is not True:
                if os.path.exists(filepath):
                    os.remove(filepath)
        except Exception:
            error_msg = 'Warning: PubmedScraper: Could not retrieve text data from pdf for id:'
            write_to_log(self.element_id, self.__class__.__name__, error_msg)
            print('Warning: PubmedScraper: Could not retrieve text data from pdf for id:', end=' ')
            print(self.element_id)
            # print('Error message: ' + repr(e))

        return text

    # ---------------------------------------------------------
    # MARK: _scrape, get_ids
    # ---------------------------------------------------------

    def get_documents(self, data: TypePubMedScrappingData) -> List[Document]:
        # Full-text PDFs frequently can't be downloaded (publisher paywalls / missing
        # Wiley/Elsevier API tokens). Fall back to the abstract — which PubMed always
        # returns — so the article still contributes something to the vector store.
        transcript = (data.get('transcript') or '').strip()
        abstract = (data.get('abstract') or '').strip()
        content = transcript or abstract
        if not content:
            return []
        chunks = get_text_chunks(content)
        metadata = {
            'abstract': data.get('abstract', ''),
            'authors': data.get('authors', ''),
            'publicationDate': data.get('publicationDate', ''),
            'title': data.get('title', ''),
            'ref': data.get('ref', ''),
            'source': 'pubmed',
            'pmid': self.element_id,
            'disease': self.disease,
            'full_text': bool(transcript),
        }
        documents = [Document(page_content=chunk, metadata=metadata) for chunk in chunks]
        return documents

    def _scrape(self) -> TypePubMedScrappingData:
        try:
            metadata = self.fetch_details(self.element_id)

            title = self.get_title_from_details(metadata)
            authors = self.get_authors_from_details(metadata)
            publication_date = self.get_publication_date_from_details(metadata)
            doi = self.get_doi_from_details(metadata)
            abstract = self.get_abstract_from_details(metadata)

            file_name = self.get_paper_from_doi(doi, title)
            text_data = self.get_txt_from_pdf(file_name)

            data: TypePubMedScrappingData = {
                'abstract': abstract,
                'authors': authors,
                'publicationDate': publication_date,
                'ref': doi,
                'title': title,
                'transcript': text_data,
            }
        except Exception as e:
            write_to_log(
                self.element_id, self.__class__.__name__, f'Error occured in PubmedScraper: {e}'
            )
            print(f'Error occured in PubmedScraper: {e}')
            data = {}
        return data

    def _record_scraped(self, scrapped_dict: TypePubMedScrappingData, documents: List[Document]):
        """Record this paper in the global dedup ledger (Firestore, or local fallback)."""
        ledger.record(
            self.element_id,
            doi=scrapped_dict.get('ref'),
            title=scrapped_dict.get('title'),
            disease=self.disease,
            chunk_count=len(documents),
            full_text=bool((scrapped_dict.get('transcript') or '').strip()),
            source='pubmed',
        )

    @classmethod
    def get_all_possible_elements(cls, target) -> List[BaseScraper]:
        query_str = ' '.join(target.keywords)
        candidates = set(cls.search_free_fulltext(query_str, target.max_results))
        # Dedup against the global ledger BEFORE downloading/embedding anything.
        new_target_elements = ledger.filter_new(candidates)
        disease = getattr(target, 'disease', None)
        return [PubMedScraper(element_id=id, disease=disease) for id in new_target_elements]
