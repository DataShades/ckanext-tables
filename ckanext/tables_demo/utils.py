from faker import Faker


def generate_mock_data(num_records: int) -> list[dict[str, str]]:
    fake = Faker()

    return [
        {
            "id": str(i),
            "name": fake.first_name(),
            "surname": fake.last_name(),
            "email": fake.email(),
            "created": fake.date_time_this_decade().isoformat(),
        }
        for i in range(1, num_records + 1)
    ]
