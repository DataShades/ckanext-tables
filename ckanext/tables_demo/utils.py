from faker import Faker

ARTICLE_STATUSES = ["draft", "review", "published"]
ARTICLE_TAGS = ["climate", "economy", "education", "energy", "health", "housing", "transport", "water"]


def generate_mock_data(num_records: int) -> list[dict[str, str | bool]]:
    fake = Faker()

    return [
        {
            "id": str(i),
            "name": fake.first_name(),
            "surname": fake.last_name(),
            "email": fake.email(),
            "sysadmin": False,
            "created": fake.date_time_this_decade().isoformat(),
        }
        for i in range(1, num_records + 1)
    ]


def generate_mock_articles(num_records: int) -> list[dict[str, str | bool | list[str]]]:
    fake = Faker()

    return [
        {
            "id": str(i),
            "title": fake.sentence(nb_words=6).rstrip("."),
            "author": fake.name(),
            "status": fake.random_element(ARTICLE_STATUSES),
            # a list cell: the "tag" quick filter matches any of its items
            "tags": fake.random_elements(ARTICLE_TAGS, length=fake.random_int(1, 3), unique=True),
            "pinned": False,
            "updated": fake.date_time_this_year().isoformat(),
        }
        for i in range(1, num_records + 1)
    ]


def generate_mock_products(num_records: int) -> list[dict[str, str | bool]]:
    fake = Faker()
    categories = ["Electronics", "Books", "Clothing", "Home & Garden", "Toys", "Sports"]

    return [
        {
            "id": str(i),
            "name": fake.catch_phrase(),
            "category": fake.random_element(categories),
            "price": str(fake.pydecimal(left_digits=3, right_digits=2, positive=True, min_value=5)),
            "in_stock": fake.boolean(chance_of_getting_true=75),
            "supplier": fake.company(),
        }
        for i in range(1, num_records + 1)
    ]
