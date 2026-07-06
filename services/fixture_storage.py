from database.fixture_repository import FixtureRepository


class FixtureStorage:

    def __init__(self):
        self.repository = FixtureRepository()

    def save(self, fixtures):

        self.repository.save_many(fixtures)

        print(f"✓ Saved {len(fixtures)} fixtures.")
