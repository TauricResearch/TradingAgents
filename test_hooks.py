def poorly_formatted_function(x, y, z):  # Missing type hints
    """This function has formatting issues."""
    result = x + y * z  # Missing spaces around operators
    if result > 100:  # Missing spaces
        print("Result is large")  # Extra spaces in parentheses
    return result


# Long line that Black will wrap
very_long_variable_name_that_exceeds_the_standard_line_length_limit = (
    "This is a very long string that will be wrapped by Black formatter"
)


class MyClass:
    def __init__(self, name: str, age: int):  # Missing space after comma
        self.name = name  # Missing spaces around =
        self.age = age


# Function with wrong return type hint
def get_number() -> str:
    return 123  # Returns int but type hint says str
