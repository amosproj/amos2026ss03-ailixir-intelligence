import json
import os
import time
from datetime import datetime, timezone
from typing import List

import requests
from bs4 import BeautifulSoup
from langchain.schema import Document

# Paths for raw data and index file
RAW_DIR_PATH = os.path.join('data', 'nutrition_recipe', 'raw')
INDEX_FILE_PATH = os.path.join('data', 'nutrition_recipe', 'index.json')

# Ensure directories and index file exist
os.makedirs(RAW_DIR_PATH, exist_ok=True)
if not os.path.exists(INDEX_FILE_PATH):
    with open(INDEX_FILE_PATH, 'w') as f:
        f.write(json.dumps({'indexes': []}, indent=2))


class RecipeScraper:
    INDEX = json.loads(open(INDEX_FILE_PATH).read())
    url = ''
    max_pages = None

    def __init__(self, link: str):
        self.link = link

    @classmethod
    def search_recipe_links(cls) -> List[str]:
        """Search the recipe site for recipe links and return them as a list of URLs."""
        page_number = 1
        recipe_links = set()
        while True:
            print(f'Scraping page {page_number}')
            page_url = cls.url if page_number == 1 else f'{cls.url}/page/{page_number}/'
            response = requests.get(page_url)
            soup = BeautifulSoup(response.content, 'html.parser')

            links = soup.find_all('a', class_='wpupg-item-link')
            if not links:
                print('No more recipes found.')
                break

            for link in links:
                href = link.get('href')
                if href:
                    recipe_links.add(href)

            page_number += 1
            # Add a delay if needed to avoid overwhelming the server
            time.sleep(2)
            # Check if we reached the last page or maximum number of pages to scrape
            if len(links) == 0 or (cls.max_pages is not None and page_number > cls.max_pages):
                break

        return list(recipe_links)

    @staticmethod
    def fetch_recipe_details(url: str) -> dict:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')

        # Extracting ingredients
        ingredients = []
        ingredient_items = soup.find_all('span', class_='wprm-recipe-ingredient-name')
        for item in ingredient_items:
            ingredients.append(item.text.strip())

        # Extracting instructions
        instructions = []
        instruction_items = soup.find_all('div', class_='wprm-recipe-instruction-text')
        for item in instruction_items:
            instructions.append(item.text.strip())

        # Extracting author details
        author_element = soup.find(
            'span', class_='wprm-recipe-details wprm-recipe-author wprm-block-text-light'
        )
        if author_element and author_element.find('a'):
            author = author_element.find('a').text.strip()
            author_link = author_element.find('a')['href']
        else:
            author = 'Author details not found'
            author_link = 'Author link not found'

        recipe_details = {
            'url': url,
            'title': soup.find('h1', class_='entry-title').text.strip(),
            'ingredients': ingredients,
            'instructions': instructions,
            'author': author,
            'author_link': author_link,
        }

        return recipe_details

    @staticmethod
    def save_recipes_to_json(recipes: List[dict], filename='recipe_details.json'):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(recipes, f, ensure_ascii=False, indent=4)

    @classmethod
    def get_documents(cls, data: dict) -> List[Document]:
        ingredients = data.get('ingredients', [])
        instructions = data.get('instructions', [])
        if isinstance(ingredients, list):
            ingredients = ' '.join(ingredients)

        if isinstance(instructions, list):
            instructions = ' '.join(instructions)

        ingredients_chunks = cls.get_text_chunks(ingredients)
        instructions_chunks = cls.get_text_chunks(instructions)

        metadata = {
            'domain': 'medical',
            'sub_domain': 'nutrition',
            'query_keywords': [],
            'document_keywords': [],
            'source': 'nutritionfacts_recipe',
            'source_type': 'recipe',
            'published_date': str(data.get('date', '') or ''),
            'ingested_at': datetime.now(timezone.utc).isoformat(),
            'author': data.get('author', ''),
            'title': data.get('title', ''),
            'ref': data.get('ref', ''),
        }
        ingredients_documents = [
            Document(
                page_content=chunk,
                metadata={**metadata, 'type': 'ingredients', 'content_section': 'ingredients'},
            )
            for chunk in ingredients_chunks
        ]
        instructions_documents = [
            Document(
                page_content=chunk,
                metadata={**metadata, 'type': 'instructions', 'content_section': 'instructions'},
            )
            for chunk in instructions_chunks
        ]
        documents = ingredients_documents + instructions_documents
        return documents

    @classmethod
    def get_text_chunks(cls, text: str, max_length: int = 80) -> List[str]:
        return [text[i : i + max_length] for i in range(0, len(text), max_length)]

    def _scrape(self) -> dict:
        final_url = self.link
        print(f'Scraping {final_url}')
        soup = BeautifulSoup(final_url, 'html.parser')

        ingredients = []
        ingredient_items = soup.find_all('span', class_='wprm-recipe-ingredient-name')
        for item in ingredient_items:
            ingredients.append(item.text.strip())

        # Extracting instructions
        instructions = []
        instruction_items = soup.find_all('div', class_='wprm-recipe-instruction-text')
        for item in instruction_items:
            instructions.append(item.text.strip())

        # Extracting author details
        author_element = soup.find(
            'span', class_='wprm-recipe-details wprm-recipe-author wprm-block-text-light'
        )
        if author_element and author_element.find('a'):
            author = author_element.find('a').text.strip()
            author_link = author_element.find('a')['href']
        else:
            author = 'Author details not found'
            author_link = 'Author link not found'

            recipe_details = {
                'url': final_url,
                'ingredients': ingredients,
                'instructions': instructions,
                'author': author,
                'author_link': author_link,
            }

        return recipe_details

    @classmethod
    def get_all_possible_elements(cls, target) -> List['RecipeScraper']:
        cls.url = target.url

        old_indexes = set(cls.INDEX['indexes'])
        new_links = set(cls.search_recipe_links())
        new_target_elements = new_links - old_indexes
        return [RecipeScraper(link=link) for link in new_target_elements]

    @staticmethod
    def update_index(new_links: List[str]):
        with open(INDEX_FILE_PATH, 'r+') as f:
            index_data = json.load(f)
            index_data['indexes'].extend(new_links)
            f.seek(0)
            json.dump(index_data, f, ensure_ascii=False, indent=2)
            f.truncate()


def main():
    url = 'https://nutritionfacts.org/recipes/'
    RecipeScraper.url = url

    # Fetch new recipe links
    new_elements = RecipeScraper.get_all_possible_elements(target=RecipeScraper)
    new_links = [element.link for element in new_elements]

    # Scrape new recipes and update index
    recipes = []
    for element in new_elements:
        recipe_data = element._scrape()
        if recipe_data:
            recipes.append(recipe_data)

    # Save scraped recipes to JSON file
    RecipeScraper.save_recipes_to_json(recipes)
    print(f'Successfully saved details of {len(recipes)} recipes to recipe_details.json')

    # Update the index with new recipe links
    RecipeScraper.update_index(new_links)

    # Save recipes to a temporary file and read it for printing
    with open('temp_recipe_details.json', 'w', encoding='utf-8') as f:
        json.dump(recipes, f, ensure_ascii=False, indent=4)

    with open('temp_recipe_details.json', 'r', encoding='utf-8') as f:
        print(f.read())


if __name__ == '__main__':
    main()
