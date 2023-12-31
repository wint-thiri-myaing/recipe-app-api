"""
test for recipe APIs
"""
from decimal import Decimal
import tempfile
import os

from PIL import Image

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Recipe,
    Tag,
    Ingredient,
)

from recipe.serializers import (
    RecipeSerializer,
    RecipeDetailSerializer,
)

RECIPES_URL = reverse('recipe:recipe-list')

def detail_url(recipe_id):
    """create and return recipe detail url"""
    return reverse('recipe:recipe-detail', args=[recipe_id])

def image_upload_url(recipe_id):
    """create and return image upload url"""
    return reverse('recipe:recipe-upload-image', args=[recipe_id])


def create_recipe(user, **params):
    """create and return sample recipe"""
    defaults = {
        'title': 'sample recipe title',
        'time_minutes': 22,
        'price': Decimal('5.25'),
        'description':'sample description',
        'link':'http://example.com/recipe.pdf',
    }
    defaults.update(params)

    recipe = Recipe.objects.create(user = user, **defaults)
    return recipe

def create_user(**params):
    """create and return a new user"""
    return get_user_model().objects.create_user(**params)

class PublicRecipeAPITests(TestCase):
    """test unauthenticated api requests"""

    def setUp(self):
        self.client = APIClient()


    def test_auth_required(self):
        """test auth is required to call api"""
        res = self.client.get(RECIPES_URL)

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

class PrivateRecipeAPITests(TestCase):
    """test authenticated api request"""
    def setUp(self):
        self.client = APIClient()
        self.user = create_user(email = 'user@example.com', password = 'test123')
        # self.user = get_user_model().objects.create_user(
        #     'user@example.com',
        #     'testpass123'
        # )

        self.client.force_authenticate(self.user)

    def test_retrive_recipes(self):
        """test retriving a list of recipes"""
        create_recipe(user=self.user)
        create_recipe(user=self.user)

        res = self.client.get(RECIPES_URL)

        recipes = Recipe.objects.all().order_by('-id')
        serializer = RecipeSerializer(recipes, many=True)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_recipe_list_limited_to_user(self):
        """test list of recipe is limited for authenticate user"""
        other_user = create_user(email = 'other@example.com', password = 'test123')
        # other_user = get_user_model().objects.create_user(
        #     'other@example.com',
        #     'password123'
        # )
        create_recipe(user=other_user)
        create_recipe(user=self.user)

        res = self.client.get(RECIPES_URL)

        recipes = Recipe.objects.filter(user = self.user)
        serializer = RecipeSerializer(recipes, many=True)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_get_recipe_detail(self):
        """test get recipe details"""
        recipe = create_recipe(user=self.user)

        url = detail_url(recipe.id)
        res = self.client.get(url)

        serializer = RecipeDetailSerializer(recipe)
        self.assertEqual(res.data, serializer.data)

    def test_create_recipe(self):
        """test creating a recipe"""
        payload = {
            'title':'sample recipe',
            'time_minutes': 30,
            'price': Decimal('5.99'),
        }

        res = self.client.post(RECIPES_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        recipe = Recipe.objects.get(id = res.data['id'])
        for k, v in payload.items():
            self.assertEqual(getattr(recipe, k), v)
        self.assertEqual(recipe.user, self.user)

    def test_partial_update(self):
        """test partial update of recipe"""
        original_link = 'https://example.com/recipe.pdf'
        recipe = create_recipe(
            user = self.user,
            title = 'sample recipe title',
            link = original_link,
        )
        payload = { 'title': 'new recipe title' }
        url = detail_url(recipe.id)
        res = self.client.patch(url, payload)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        recipe.refresh_from_db()
        self.assertEqual(recipe.title, payload['title'])
        self.assertEqual(recipe.link, original_link)
        self.assertEqual(recipe.user, self.user)

    def test_full_update(self):
        """test full update for a recipe"""
        recipe = create_recipe(
            user = self.user,
            title = 'sample recipe title',
            link = 'https://example.com/recipe.pdf',
            description = 'sample recipe description',
        )
        payload = {
            'title': 'new recipe title',
            'link': 'https://example.com/recipe.pdf',
            'description' :'sample recipe description',
            'time_minutes': 10,
            'price': Decimal('2.50'),
        }
        url = detail_url(recipe.id)
        res = self.client.put(url, payload)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        recipe.refresh_from_db()
        for k, v in payload.items():
            self.assertEqual(getattr(recipe, k), v)
        self.assertEqual(recipe.user, self.user)

    def test_update_user_return_error(self):
        """test changing the recipe user results in an error"""
        new_user = create_user(email = 'user2@example.com', password = 'test123')
        recipe = create_recipe(user=self.user)

        payload = {
            'user': new_user.id
        }
        url = detail_url(recipe.id)
        self.client.patch(url, payload)

        recipe.refresh_from_db()
        self.assertEqual(recipe.user, self.user)

    def test_delete_recipe(self):
        """test delete recipe successful"""
        recipe = create_recipe(user=self.user)

        url = detail_url(recipe.id)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Recipe.objects.filter(id = recipe.id).exists())

    def test_delete_other_users_recipe_error(self):
        """test trying to delete another user recipe give error"""
        new_user = create_user(email = 'user2@example.com', password = 'test123')
        recipe = create_recipe(user=new_user)

        url = detail_url(recipe.id)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Recipe.objects.filter(id = recipe.id).exists())

    def test_create_recipe_with_new_tags(self):
        """test creating a recipe with new tag"""
        payload = {
            'title': 'Thai prawn cuerry',
            'time_minutes': 30,
            'price': Decimal('2.50'),
            'tags': [{'name':'Thai'}, {'name':'Dinner'}]
        }
        res = self.client.post(RECIPES_URL, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        recipes = Recipe.objects.filter(user= self.user)
        self.assertEqual(recipes.count(), 1)
        recipe = recipes[0]
        self.assertEqual(recipe.tags.count(), 2)
        for tag in payload['tags']:
             exists = recipe.tags.filter(
                 name = tag['name'],
                 user = self.user,
             ).exists()
             self.assertTrue(exists)

    def test_create_recipe_with_existing_tags(self):
        """test creating a recipe with existing tags"""
        tag_indian = Tag.objects.create(user=self.user, name='Indian')
        payload = {
            'title': 'Pongal',
            'time_minutes': 60,
            'price': Decimal('4.50'),
            'tags': [{'name':'Indian'}, {'name':'Breakfast'}]
        }
        res = self.client.post(RECIPES_URL, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        recipes = Recipe.objects.filter(user= self.user)
        self.assertEqual(recipes.count(), 1)
        recipe = recipes[0]
        self.assertEqual(recipe.tags.count(), 2)
        self.assertIn(tag_indian, recipe.tags.all())
        for tag in payload['tags']:
             exists = recipe.tags.filter(
                 name = tag['name'],
                 user = self.user,
             ).exists()
             self.assertTrue(exists)

    def test_create_tag_on_update(self):
        """test creating tag when updating a recipe"""
        recipe = create_recipe(user=self.user)

        payload = {'tags':[{'name':'Lunch'}]}
        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        new_tag = Tag.objects.get(user = self.user, name='Lunch')
        self.assertIn(new_tag, recipe.tags.all())

    def test_update_recipe_assign_tag(self):
        """test assigining an existing tag when updaing a recipe"""
        tag_breakfast = Tag.objects.create(user= self.user, name='Breakfast')
        recipe = create_recipe(user=self.user)
        recipe.tags.add(tag_breakfast)

        tag_lunch = Tag.objects.create(user= self.user, name='Lunch')
        payload = {'tags':[{'name':'Lunch'}]}
        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(tag_lunch, recipe.tags.all())
        self.assertNotIn(tag_breakfast, recipe.tags.all())

    def test_clear_recipe_tags(self):
        """test clearing recipe tag"""
        tag = Tag.objects.create(user= self.user, name='Dessert')
        recipe = create_recipe(user=self.user)
        recipe.tags.add(tag)

        payload = {'tags':[]}
        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(recipe.tags.count(), 0)

    def test_create_recipe_with_new_ingredients(self):
        """test creating a recipe with new ingredients"""
        payload = {
            'title': 'Mala',
            'time_minutes': 50,
            'price': Decimal('6.50'),
            'ingredients': [{'name':'Noodle'}, {'name':'Meat ball'}]
        }
        res = self.client.post(RECIPES_URL, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        recipes = Recipe.objects.filter(user= self.user)
        self.assertEqual(recipes.count(), 1)
        recipe = recipes[0]
        self.assertEqual(recipe.ingredients.count(), 2)
        for ingredient in payload['ingredients']:
            exists = recipe.ingredients.filter(
                name = ingredient['name'],
                user = self.user,
            ).exists()
            self.assertTrue(exists)

    def test_create_recipe_with_existing_ingredients(self):
        """test creating a recipe with existing ingredients"""
        ingredient = Ingredient.objects.create(user=self.user, name='Lemon')
        payload = {
            'title': 'Vietnames soup',
            'time_minutes': 25,
            'price': Decimal('2.55'),
            'ingredients': [{'name':'Lemon'}, {'name':'Fish sause'}]
        }
        res = self.client.post(RECIPES_URL, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        recipes = Recipe.objects.filter(user= self.user)
        self.assertEqual(recipes.count(), 1)
        recipe = recipes[0]
        self.assertEqual(recipe.ingredients.count(), 2)
        self.assertIn(ingredient, recipe.ingredients.all())
        for ingredient in payload['ingredients']:
            exists = recipe.ingredients.filter(
                name = ingredient['name'],
                user = self.user,
            ).exists()
            self.assertTrue(exists)

    def test_create_ingredients_on_update(self):
        """test creating ingredients when updating a recipe"""
        recipe = create_recipe(user=self.user)

        payload = {'ingredients':[{'name':'Limes'}]}
        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        new_ingredient = Ingredient.objects.get(user = self.user, name='Limes')
        self.assertIn(new_ingredient, recipe.ingredients.all())

    def test_update_recipe_assign_ingredient(self):
        """test assigining an existing ingredient when updaing a recipe"""
        ingredient1 = Ingredient.objects.create(user= self.user, name='Pepper')
        recipe = create_recipe(user=self.user)
        recipe.ingredients.add(ingredient1)

        ingredient2 = Ingredient.objects.create(user= self.user, name='Chili')
        payload = {'ingredients':[{'name':'Chili'}]}
        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(ingredient2, recipe.ingredients.all())
        self.assertNotIn(ingredient1, recipe.ingredients.all())

    def test_clear_recipe_ingredients(self):
        """test clearing recipe ingredients"""
        ingredient = Ingredient.objects.create(user= self.user, name='Garlic')
        recipe = create_recipe(user=self.user)
        recipe.ingredients.add(ingredient)

        payload = {'ingredients':[]}
        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(recipe.ingredients.count(), 0)

    def test_filter_by_tags(self):
        """test filtering recipes by tag"""
        r1 = create_recipe(user=self.user, title='Thai Vegetable Currery')
        r2 = create_recipe(user=self.user, title='Thai Salad')
        tag1 = Tag.objects.create(user=self.user, name='Vegan')
        tag2 = Tag.objects.create(user=self.user, name='Vegetarian')
        r1.tags.add(tag1)
        r2.tags.add(tag2)
        r3 = create_recipe(user=self.user, title='Fish and Chip')

        params = {'tags': f'{tag1.id}, {tag2.id}'}
        res = self.client.get(RECIPES_URL, params)

        s1 = RecipeSerializer(r1)
        s2 = RecipeSerializer(r2)
        s3 = RecipeSerializer(r3)
        self.assertIn(s1.data, res.data)
        self.assertIn(s2.data, res.data)
        self.assertNotIn(s3.data, res.data)

    def test_filter_by_ingredients(self):
        """test filtering recipes by ingredients"""
        r1 = create_recipe(user=self.user, title='Beans on toach')
        r2 = create_recipe(user=self.user, title='Chicken on toach')
        in1 = Ingredient.objects.create(user=self.user, name='Feta Cheese')
        in2 = Ingredient.objects.create(user=self.user, name='Chicken')
        r1.ingredients.add(in1)
        r2.ingredients.add(in2)
        r3 = create_recipe(user=self.user, title='Red lental deal')

        params = {'ingredients': f'{in1.id}, {in2.id}'}
        res = self.client.get(RECIPES_URL, params)

        s1 = RecipeSerializer(r1)
        s2 = RecipeSerializer(r2)
        s3 = RecipeSerializer(r3)
        self.assertIn(s1.data, res.data)
        self.assertIn(s2.data, res.data)
        self.assertNotIn(s3.data, res.data)





class ImageUploadTests(TestCase):
    """test for image upload api"""
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            'user@example.com',
            'password123',
        )
        self.client.force_authenticate(self.user)
        self.recipe = create_recipe(user=self.user)

    def tearDown(self):
        self.recipe.image.delete()

    def test_upload_image(self):
        """test uploading an image to recipe"""
        url = image_upload_url(self.recipe.id)
        with tempfile.NamedTemporaryFile(suffix='.jpg') as image_file:
            img = Image.new('RGB', (10, 10))
            img.save(image_file, format='JPEG')
            image_file.seek(0)
            payload = {'image': image_file}
            res = self.client.post(url, payload, format= 'multipart')

        self.recipe.refresh_from_db()
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('image', res.data)
        self.assertTrue(os.path.exists(self.recipe.image.path))

    def test_upload_image_bad_request(self):
        """test uploading invalid image"""
        url = image_upload_url(self.recipe.id)
        payload = {'image': 'notImage'}
        res = self.client.post(url, payload, format= 'multipart')

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)





















