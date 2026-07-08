import json
import logging
import os
from typing import List

from langchain_core.documents import Document

from src.backend.log.log import write_to_log
from src.backend.Scrapers.BaseScraper.base_scraper import BaseScraper
from src.backend.Scrapers.PubMed import INDEX_FILE_PATH, RAW_DIR_PATH
from src.backend.Types.pub_med import TypePubMedScrappingData
from src.backend.Utils.splitter import get_text_chunks

logging.getLogger('paperscraper').setLevel(logging.ERROR)  # suppress warnings

from Bio import Entrez  # noqa: E402
from paperscraper.pdf import save_pdf  # noqa: E402
from pypdf import PdfReader  # noqa: E402


class PubMedScraper(BaseScraper):
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
    # MARK: Pubmed Queries
    # ---------------------------------------------------------

    """Get Pubmed ID's for a search query (eg. 'nutrition cancer').

  only retrieves free full text papers (filter)
  can only retrieve the first 10k search results so be specific with search terms"""

    @classmethod
    def search_free_fulltext(cls, query: str, max_results=10_000, since_date=None):
        Entrez.email = os.getenv('NCBI_EMAIL', 'email@example.com')
        Entrez.api_key = os.getenv('NCBI_API_KEY') or None
        date_filters = {}
        if since_date:
            date_filters = {
                'mindate': since_date.replace('-', '/'),
                'maxdate': '3000/12/31',
                'datetype': 'pdat',
            }
        handle = Entrez.esearch(
            db='pubmed',
            sort='pub date' if since_date else 'relevance',
            retmax=max_results,
            retmode='xml',
            term=query + ' AND free full text[sb]',
            **date_filters,
        )
        # optionally: could further filter with mindate and maxdate args,
        # see docs: https://www.ncbi.nlm.nih.gov/books/NBK25499/
        results = Entrez.read(handle)
        handle.close()
        return results['IdList']

    """Get metadata for one pubmed id, received from search query.

  Metadata is stored in a dictionary"""

    def fetch_details(self, id):
        Entrez.email = os.getenv('NCBI_EMAIL', 'email@example.com')
        Entrez.api_key = os.getenv('NCBI_API_KEY') or None
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

    def get_keywords_from_details(self, details_dict):
        keywords = []
        try:
            citation = details_dict['PubmedArticle'][0]['MedlineCitation']
            for heading in citation.get('MeshHeadingList', []):
                descriptor = heading.get('DescriptorName')
                if descriptor:
                    keywords.append(str(descriptor))
                for qualifier in heading.get('QualifierName', []):
                    keywords.append(str(qualifier))
        except Exception as e:
            print('Error: pubmed_scraping: get_keywords_from_details: Could not retrieve MeSH.')
            print(e)

        try:
            article = details_dict['PubmedArticle'][0]['MedlineCitation']['Article']
            for keyword_list in article.get('KeywordList', []):
                keywords.extend(str(keyword) for keyword in keyword_list)
        except Exception as e:
            print(
                'Error: pubmed_scraping: get_keywords_from_details:'
                + ' Could not retrieve author keywords.'
            )
            print(e)

        return sorted(set(keywords))

    # ---------------------------------------------------------
    # MARK: Get pdf and text
    # ---------------------------------------------------------

    def get_paper_from_doi(self, doi: str, title=None, path='papers'):
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
        filepath = path + '/' + filename

        save_pdf(paper_data, filepath=filepath + '.pdf')
        return filename

    def get_txt_from_pdf(
        self, filename: str, path='papers/', create_txt_file=False, keep_pdfs=False
    ):
        text = ''
        try:
            filepath = path + f'{filename}.pdf'
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
        transcript = data.get('transcript', '')
        chunks = get_text_chunks(transcript)
        metadata = {
            **self._common_metadata(
                source='pubmed',
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
            'doi': data.get('doi', data.get('ref', '')),
        }
        documents = [Document(page_content=chunk, metadata=metadata) for chunk in chunks]
        return documents

    def _scrape(self) -> TypePubMedScrappingData:
        try:
            metadata = getattr(self, '_discovered_metadata', None) or self.fetch_details(
                self.element_id
            )

            title = self.get_title_from_details(metadata)
            authors = self.get_authors_from_details(metadata)
            publication_date = self.get_publication_date_from_details(metadata)
            doi = self.get_doi_from_details(metadata)
            abstract = self.get_abstract_from_details(metadata)
            document_keywords = self.get_keywords_from_details(metadata)

            text_data = ''
            if doi:
                file_name = self.get_paper_from_doi(doi, title)
                text_data = self.get_txt_from_pdf(file_name)

            # Abstracts remain useful and embeddable when full text is unavailable.
            text_data = text_data.strip() or abstract.strip() or title.strip()

            data: TypePubMedScrappingData = {
                'abstract': abstract,
                'authors': authors,
                'publicationDate': publication_date,
                'documentKeywords': document_keywords,
                'ref': doi,
                'doi': doi,
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

    @classmethod
    def get_all_possible_elements(cls, target) -> List[BaseScraper]:
        with open(cls.index_file(), encoding='utf-8') as file:
            old_indexes = set(json.load(file).get('indexes', []))
        query_str = ' '.join(target.keywords)
        new_indexes = set(
            cls.search_free_fulltext(query_str, target.max_results, target.since_date)
        )
        new_target_elements = new_indexes - old_indexes
        candidates = [
            PubMedScraper(
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
                metadata = candidate.fetch_details(candidate.element_id)
                identity = {
                    'title': candidate.get_title_from_details(metadata),
                    'doi': candidate.get_doi_from_details(metadata),
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
                candidate._discovered_metadata = metadata
            except Exception:
                # Let the normal scrape path report detailed source errors.
                pass
            accepted.append(candidate)
        return accepted
