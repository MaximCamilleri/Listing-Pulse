from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Scraper 
    scraper_url:str = Field(default="", description="")
    scraper_search_term:str = Field(default="", description="")
    scraper_cooldown:float = Field(default=10.0, description="Time between checks in seconds")
    scraper_cooldown_offset:float = Field(default=2.5, description="Plus or minus seconds from scraper_cooldown")
    scraper_timeout:float = Field(default=5.0, description="Max time the scraper can taker to respond")

    

class Config:
    env_file = ".env"
    env_file_encoding = "utf-8"
    case_sensitive = False 
    env_prefix = ""
    populate_by_name = True 

settings = Settings()