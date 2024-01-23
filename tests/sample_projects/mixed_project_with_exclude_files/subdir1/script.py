from requests import Request, Session

pyproject_url = "https://raw.githubusercontent.com/tweag/nickel/master/Cargo.toml"
s = Session()
req = Request("GET", pyproject_url)
prepped = req.prepare()
timeout = 10
resp = s.send(prepped, timeout=timeout)

print(f"GET {pyproject_url} => {resp.status_code}")
print(resp.text)
