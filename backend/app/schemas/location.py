from pydantic import BaseModel, computed_field

from app.modules.universities.city_time import city_time_zone


class CityLocation(BaseModel):
    city: str | None = None

    @computed_field(
        description="IANA-зона по городу; null для неизвестного или неоднозначного города."
    )
    @property
    def time_zone(self) -> str | None:
        return city_time_zone(self.city)
