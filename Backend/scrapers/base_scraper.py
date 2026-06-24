import json
import os
from abc import ABCMeta, abstractmethod
from typing import List

from langchain_astradb import AstraDBVectorStore
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from .log import write_to_log
from .types import TypeBaseScrappingData


class BaseScraper(metaclass=ABCMeta):
    def __init__(self, element_id: str):
        self.element_id = element_id

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
        indexes: List[str] = json.loads(open(self.index_file(), 'r').read()).get('indexes', [])
        return self.element_id in indexes

    def _save(self, scrapped_dict: dict):
        file_path = os.path.join(self.base_dir(), f'{self.element_id}.json')
        with open(file_path, 'w') as file:
            json.dump(scrapped_dict, file, indent=2)

    def _save_vector_docs(self, documents: List[Document]):
        vector_store = AstraDBVectorStore(
            embedding=OpenAIEmbeddings(api_key=os.getenv('OPEN_AI_API')),
            api_endpoint=os.getenv('ASTRA_DB_API_ENDPOINT'),
            token=os.getenv('ASTRA_DB_TOKEN'),
            namespace=os.getenv('ASTRA_DB_NAMESPACE'),
            collection_name=os.getenv('ASTRA_DB_COLLECTION'),
        )
        vector_store.add_documents(documents=documents)

    def scrape_and_save(self):
        scrapped_dict = self._scrape()
        # Check if the scrapped_dict is empty
        if not scrapped_dict:
            print(f'No data found for {self.element_id}')
            write_to_log(
                self.element_id, self.__class__.__name__, f'No data found for {self.element_id}'
            )
            return
        # save scrapped json file
        self._save(scrapped_dict)
        # create chunk documents
        documents = self.get_documents(scrapped_dict)
        # Save the vector documents
        self._save_vector_docs(documents)
        # Mark this element as ingested (dedup ledger)
        self._record_scraped(scrapped_dict, documents)

    def _record_scraped(self, scrapped_dict: dict, documents: List[Document]):
        """Mark this element as ingested. Override to use a richer dedup ledger.

        Default: append the element_id to the local JSON index file.
        """
        with open(type(self).index_file(), 'r+') as file:
            index_data = json.load(file)
            indexes = index_data.get('indexes', [])
            indexes.append(self.element_id)
            index_data['indexes'] = indexes
            # Write the updated index data back to the file
            file.seek(0)
            json.dump(index_data, file, indent=2)
