from app.core.exceptions import NotFound
from app.modules.universities.repository import UniversityRepository
from app.modules.universities.schemas import UniversityCreate, UniversityUpdate


class UniversityService:
    def __init__(self, repo: UniversityRepository):
        self.repo = repo

    def list(self, q=None, region=None):
        return self.repo.list(q=q, region=region)

    def get(self, university_id: int):
        obj = self.repo.get(university_id)
        if not obj:
            raise NotFound("University not found")
        return obj

    def create(self, data: UniversityCreate):
        return self.repo.create(data)

    def update(self, university_id: int, data: UniversityUpdate):
        obj = self.get(university_id)
        return self.repo.update(obj, data)
