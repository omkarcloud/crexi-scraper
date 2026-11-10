"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. Params go through the same schemas the API uses, so defaults
are filled in and a Crexi id or link both work.
"""
import json
import os

from crexi import api, schemas

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


def run(schema_cls, fn, **params):
    return fn(**schema_cls().load(params))


if __name__ == "__main__":
    # a Crexi id or any crexi.com property link — asking price, building facts, brokers and every photo
    save("property_beverly_hills_medical_office.json",
         run(schemas.PropertySchema, api.property_details, property="2345196"))

    # 20 properties for sale per page, filter by location, type, price, cap rate and size
    save("search_beverly_hills.json",
         run(schemas.PropertiesSearchSchema, api.properties_search, state="CA", city="Beverly Hills"))

    # a building for lease with every available space, its size and asking rent
    save("lease_400_s_beverly_drive.json",
         run(schemas.LeaseSchema, api.lease_details, property="389412"))
