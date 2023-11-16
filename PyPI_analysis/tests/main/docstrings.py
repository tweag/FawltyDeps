"""Example script that contains docstrings with import clause.

For example, this is a docstring for Python scripts,
and we include import clause here.

>>> import docstring_1

"""


def func():
    """
    Docstring for Python functions.

    We also include some large blocks with '...' delimiter in the docstring
    to ensure that the detection won't be stopped.

    >>> import docstring_2
    >>> from docstring_3 import d

    Examples: large blocks
    ----------------------
    >>> data = pd.DataFrame({'hr1': [514, 573], 'hr2': [545, 526],
    ...                      'team': ['Red Sox', 'Yankees'],
    ...                      'year1': [2007, 2007], 'year2': [2008, 2008]})
    >>> data
       hr1  hr2     team  year1  year2
    0  514  545  Red Sox   2007   2008
    1  573  526  Yankees   2007   2008

    >>> @dataclass
    ... class Point:
    ...     x: int
    ...     y: int

    Examples: code with syntax error
    --------------------------------
    >>> with pytest.raise(ValueError):
    ...     # Some code that raises ValueError

    >>> import docstring_4

    """
    pass


class sample:
    """Docstring for Python classes.

    We also include some large blocks with '...' delimiter in the docstring
    to ensure that the detection won't be stopped.
    Examples: large blocks

    ----------------------
    >>> data = pd.DataFrame({'hr1': [514, 573], 'hr2': [545, 526],
    ...                      'team': ['Red Sox', 'Yankees'],
    ...                      'year1': [2007, 2007], 'year2': [2008, 2008]})
    >>> data
       hr1  hr2     team  year1  year2
    0  514  545  Red Sox   2007   2008
    1  573  526  Yankees   2007   2008

    >>> @dataclass
    ... class Point:
    ...     x: int
    ...     y: int

    Examples: code with syntax error
    --------------------------------
    >>> with pytest.raise(ValueError):
    ...     # Some code that raises ValueError

    >>> import docstring_5
    """

    def __init__(self, setting):
        self.sample1 = setting
