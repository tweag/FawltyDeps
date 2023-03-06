import sys

from requests import Request, Session

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

pyproject_url = "https://raw.githubusercontent.com/tweag/nickel/master/Cargo.toml"
s = Session()
req = Request("GET", pyproject_url)
prepped = req.prepare()
timeout = 10
resp = s.send(prepped, timeout=timeout)

print(f"GET {pyproject_url} => {resp.status_code}")
cargo = tomllib.loads(resp.text)
print()
print(f"{cargo['package']['name']} v{cargo['package']['version']}")
