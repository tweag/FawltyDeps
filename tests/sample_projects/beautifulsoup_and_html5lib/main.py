from bs4 import BeautifulSoup

soup = BeautifulSoup("<html>data</html>", "html5lib")
print(soup)
