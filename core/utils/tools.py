def get_configs_kwargs(*args) -> dict[str, object]:
    kwargs = {}
    for obj in args:
        name = str(obj.__class__).split(".")[-1].removesuffix("'>")
        kwargs[name] = obj

    return kwargs
