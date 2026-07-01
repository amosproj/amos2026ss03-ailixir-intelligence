import json
import re
from typing import Dict, List

from bs4 import BeautifulSoup
from langchain.schema import Document
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from src.backend.log.log import write_to_log
from src.backend.Scrapers.AllRecipes import INDEX_FILE_PATH, RAW_DIR_PATH
from src.backend.Scrapers.BaseScraper.base_scraper import BaseScraper
from src.backend.Types.all_recipes import TypeAllRecipeScrappingData
from src.backend.Utils.splitter import get_text_chunks


class AllRecipesScraper(BaseScraper):
    INDEX = json.loads(open(INDEX_FILE_PATH).read())
    HEADERS = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        ),
        'Cookie': 'euConsent=true',
        'Accept': (
            'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,'
            'image/apng,*/*;q=0.8'
        ),
        'Accept-Language': 'en-US,en;q=0.9',
    }

    def __init__(self, element_id: str, recipe_name: str, domain='medical', sub_domain='nutrition'):
        super().__init__(element_id=element_id, domain=domain, sub_domain=sub_domain)
        base_url = AllRecipesScraper.url + 'recipe/{}/{}'
        self._url = base_url.format(element_id, recipe_name)
        try:
            self._soup = self._fetch_soup(self._url)
        except Exception as e:
            print(f'Failed to fetch data due to: {e}')
            write_to_log(
                self.element_id, self.__class__.__name__, f'Failed to fetch data due to: {e}'
            )
            self._soup = None  # Handle the case where the request fails

    @classmethod
    def _fetch_soup(cls, url: str) -> BeautifulSoup:
        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument(f'user-agent={cls.HEADERS["User-Agent"]}')
        driver = webdriver.Chrome(options=options)
        try:
            driver.get(url)
            return BeautifulSoup(driver.page_source, 'html.parser')
        finally:
            driver.quit()

    @classmethod
    def index_file(cls) -> str:
        return INDEX_FILE_PATH

    @classmethod
    def base_dir(cls) -> str:
        return RAW_DIR_PATH

    def get_heading(self) -> str:
        try:
            heading = self._soup.select_one('#article-header--recipe_1-0 > h1').get_text(strip=True)
            return heading
        except AttributeError:
            return ''

    def get_sub_heading(self) -> str:
        try:
            sub_heading = self._soup.select_one('#article-header--recipe_1-0 > p').get_text(
                strip=True
            )[1:-1]
            return sub_heading
        except AttributeError:
            return ''

    def get_rating_count(self) -> float:
        try:
            rating_count_text = self._soup.select_one(
                '#mm-recipes-review-bar__rating_1-0'
            ).get_text(strip=True)
            rating_count_number = rating_count_text[1:-1]
            return float(rating_count_number)
        except (AttributeError, ValueError):
            return 0.0

    def get_recipe_details(self) -> Dict[str, str]:
        details = {}
        try:
            items = self._soup.find_all(class_='mm-recipes-details__item')
            for item in items:
                label: str = (
                    item.find(class_='mm-recipes-details__label')
                    .get_text(strip=True)
                    .replace(':', '')
                )
                value = item.find(class_='mm-recipes-details__value').get_text(strip=True)
                details[label.replace(' ', '')] = value
        except AttributeError:
            pass
        return details

    def get_ingredients(self) -> List[str]:
        ingredients = []
        try:
            items = self._soup.find_all(class_='mm-recipes-structured-ingredients__list-item')
            for item in items:
                quantity = item.find('span', {'data-ingredient-quantity': 'true'}).get_text(
                    strip=True
                )
                unit = item.find('span', {'data-ingredient-unit': 'true'}).get_text(strip=True)
                name = item.find('span', {'data-ingredient-name': 'true'}).get_text(strip=True)
                sentence = f'{quantity} {unit} {name}'.strip()
                ingredients.append(r'{0}'.format(sentence))
        except AttributeError:
            pass
        return ingredients

    def get_steps(self) -> List[str]:
        try:
            steps = self._soup.select('.mm-recipes-steps__content ol li')
            step_list = [step.get_text(strip=True) for step in steps]
            return step_list
        except AttributeError:
            return []

    def get_nutrition_facts(self) -> Dict[str, str]:
        nutrition_dict = {}
        try:
            rows = self._soup.select('.mm-recipes-nutrition-facts-summary__table-row')
            for row in rows:
                cells = row.find_all('td', class_='mm-recipes-nutrition-facts-summary__table-cell')
                if len(cells) == 2:
                    key: str = cells[1].text.strip()
                    value = cells[0].text.strip()
                    nutrition_dict[key.replace(' ', '')] = value
        except AttributeError:
            pass
        return nutrition_dict

    def get_nutrition_info(self) -> Dict[str, Dict[str, str]]:
        nutrition_dict = {}
        try:
            rows = self._soup.select('.mm-recipes-nutrition-facts-label__table-body tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 2:
                    nutrient_name: str = (
                        cells[0]
                        .find('span', class_='mm-recipes-nutrition-facts-label__nutrient-name')
                        .text.strip()
                    )
                    nutrient_value = cells[0].contents[-1].strip()
                    daily_value = cells[1].text.strip()
                    nutrition_dict[nutrient_name.replace(' ', '')] = {
                        'Amount': nutrient_value,
                        'DailyValue': daily_value,
                    }
        except AttributeError:
            pass
        return nutrition_dict

    def get_documents(self, data: TypeAllRecipeScrappingData) -> List[Document]:
        content = '\n'.join(
            part
            for part in (
                data.get('title', ''),
                data.get('subTitle', ''),
                'Ingredients:\n' + '\n'.join(data.get('ingredients', [])),
                'Instructions:\n' + '\n'.join(data.get('steps', [])),
            )
            if part
        )
        chunks = get_text_chunks(content)
        metadata = {
            **self._common_metadata(
                source='allrecipes', source_type='recipe', published_date=''
            ),
            'subTitle': data.get('subTitle', ''),
            'rating': data.get('rating', 0.0),
            'recipeDetails': data.get('recipeDetails', {}),
            'ingredients': data.get('ingredients', []),
            'steps': data.get('steps', []),
            'nutritionFacts': data.get('nutritionFacts', {}),
            'nutritionInfo': data.get('nutritionInfo', {}),
            'ref': data.get('ref', ''),
        }
        documents = [Document(page_content=chunk, metadata=metadata) for chunk in chunks]
        return documents

    def _scrape(self) -> TypeAllRecipeScrappingData:
        scrape_data: TypeAllRecipeScrappingData = {
            'title': self.get_heading(),
            'subTitle': self.get_sub_heading(),
            'rating': self.get_rating_count(),
            'recipeDetails': self.get_recipe_details(),
            'ingredients': self.get_ingredients(),
            'steps': self.get_steps(),
            'nutritionFacts': self.get_nutrition_facts(),
            'nutritionInfo': self.get_nutrition_info(),
            'ref': self._url,
        }
        if not scrape_data['title'] or not (
            scrape_data['ingredients'] or scrape_data['steps']
        ):
            return {}
        return scrape_data

    @classmethod
    def get_all_recipes_category_urls(cls) -> List[str]:
        try:
            soup = cls._fetch_soup(cls.url)
            return list(
                dict.fromkeys(
                    link['href']
                    for link in soup.find_all('a', href=True)
                    if '/recipes/' in link['href']
                )
            )
        except Exception as e:
            print(f'Failed to fetch category URLs due to: {e}')
            error_msg = f'Failed to fetch category URLs due to: {e}'
            write_to_log(cls.url, cls.__name__, error_msg)
        return []

    @classmethod
    def get_all_recipes_of_page(cls, link_url: str, limit: int = 10) -> List[Dict[str, str]]:
        recipes = []
        try:
            soup = cls._fetch_soup(link_url)
            seen = set()
            for link in soup.find_all('a', href=True):
                match = re.search(r'/recipe/(\d+)/([^/?#]+)/?', link['href'])
                if not match or match.group(1) in seen:
                    continue
                seen.add(match.group(1))
                recipes.append({'id': match.group(1), 'name': match.group(2)})
                if len(recipes) >= limit:
                    break
        except Exception as e:
            print(f'Failed to fetch recipes from {link_url} due to: {e}')
            write_to_log(link_url, cls.__name__, f'Failed to fetch recipes due to: {e}')
        return recipes

    @classmethod
    def get_all_possible_elements(cls, target) -> List[BaseScraper]:
        cls.url = target.url
        old_indexes = set(cls.INDEX.get('indexes', []))
        # The homepage/category URL already exposes current recipe cards. Fetching
        # it once avoids many browser sessions and the site's direct-HTTP 403.
        all_recipes = cls.get_all_recipes_of_page(target.url, target.limit)
        new_recipe_ids = set(recipe['id'] for recipe in all_recipes)
        new_recipe_ids.difference_update(old_indexes)
        new_recipes = [recipe for recipe in all_recipes if recipe['id'] in new_recipe_ids]
        return [
            AllRecipesScraper(
                element_id=recipe['id'],
                recipe_name=recipe['name'],
                domain=target.domain,
                sub_domain=target.sub_domain,
            )
            for recipe in new_recipes
        ]
