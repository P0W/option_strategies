import logging

logging = logging.getLogger(__name__)


def log_function_call(func):
    def wrapper(*args, **kwargs):
        arg_list = (
            [repr(arg) for arg in args[1:]]
            if args and args[0] == "self"
            else [repr(arg) for arg in args]
        )
        kwarg_list = [f"{key}={value!r}" for key, value in kwargs.items()]
        all_args = ", ".join(arg_list + kwarg_list)
        logging.debug(f"Calling {func.__name__}({all_args})")
        result = func(*args, **kwargs)
        return result

    return wrapper
