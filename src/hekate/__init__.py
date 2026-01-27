__version__ = "1.0.0"

def Supervisor(*args, **kwargs):
    from .supervisor import Supervisor as _Supervisor
    return _Supervisor(*args, **kwargs)

def main():
    from .supervisor import main as _main
    _main()

__all__ = ["Supervisor", "main"]