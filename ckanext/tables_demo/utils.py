from faker import Faker


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
