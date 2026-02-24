from datetime import datetime
from typing import Optional


class Logger:
    
    COLORS = {
        'RESET': '\033[0m',
        'BOLD': '\033[1m',
        'RED': '\033[91m',
        'GREEN': '\033[92m',
        'YELLOW': '\033[93m',
        'BLUE': '\033[94m',
        'MAGENTA': '\033[95m',
        'CYAN': '\033[96m',
        'WHITE': '\033[97m',
        'GRAY': '\033[90m'
    }
    
    LEVEL_CONFIG = {
        'INFO': {'color': 'BLUE', 'symbol': '●'},
        'SUCCESS': {'color': 'GREEN', 'symbol': '✓'},
        'WARNING': {'color': 'YELLOW', 'symbol': '⚠'},
        'ERROR': {'color': 'RED', 'symbol': '✗'},
        'CRITICAL': {'color': 'RED', 'symbol': '⊗'},
        'DEBUG': {'color': 'GRAY', 'symbol': '○'}
    }
    
    @classmethod
    def _format_message(cls, level: str, message: str, indent: int = 0) -> str:
        config = cls.LEVEL_CONFIG.get(level, {'color': 'WHITE', 'symbol': '•'})
        color = cls.COLORS.get(config['color'], '')
        symbol = config['symbol']
        reset = cls.COLORS['RESET']
        bold = cls.COLORS['BOLD']
        
        indent_str = '  ' * indent
        level_str = f"{color}{bold}{level:<8}{reset}"
        symbol_str = f"{color}{symbol}{reset}"
        
        return f"{indent_str}{symbol_str} {level_str} {message}"
    
    @classmethod
    def info(cls, message: str, indent: int = 0):
        print(cls._format_message('INFO', message, indent))
    
    @classmethod
    def success(cls, message: str, indent: int = 0):
        print(cls._format_message('SUCCESS', message, indent))
    
    @classmethod
    def warning(cls, message: str, indent: int = 0):
        print(cls._format_message('WARNING', message, indent))
    
    @classmethod
    def error(cls, message: str, indent: int = 0):
        print(cls._format_message('ERROR', message, indent))
    
    @classmethod
    def critical(cls, message: str, indent: int = 0):
        print(cls._format_message('CRITICAL', message, indent))
    
    @classmethod
    def debug(cls, message: str, indent: int = 0):
        print(cls._format_message('DEBUG', message, indent))
    
    @classmethod
    def header(cls, title: str, width: int = 100, char: str = '='):
        border = char * width
        print(f"\n{cls.COLORS['CYAN']}{cls.COLORS['BOLD']}{border}{cls.COLORS['RESET']}")
        print(f"{cls.COLORS['CYAN']}{cls.COLORS['BOLD']}{title.center(width)}{cls.COLORS['RESET']}")
        print(f"{cls.COLORS['CYAN']}{cls.COLORS['BOLD']}{border}{cls.COLORS['RESET']}\n")
    
    @classmethod
    def section(cls, title: str, width: int = 100, char: str = '='):
        border = char * width
        print(f"\n{cls.COLORS['MAGENTA']}{cls.COLORS['BOLD']}{border}{cls.COLORS['RESET']}")
        print(f"{cls.COLORS['MAGENTA']}{cls.COLORS['BOLD']}{title}{cls.COLORS['RESET']}")
        print(f"{cls.COLORS['MAGENTA']}{cls.COLORS['BOLD']}{border}{cls.COLORS['RESET']}")
    
    @classmethod
    def subsection(cls, title: str, indent: int = 0):
        indent_str = '  ' * indent
        print(f"\n{indent_str}{cls.COLORS['CYAN']}{cls.COLORS['BOLD']}▸ {title}{cls.COLORS['RESET']}")
    
    @classmethod
    def separator(cls, width: int = 100, char: str = '-'):
        print(f"{cls.COLORS['GRAY']}{char * width}{cls.COLORS['RESET']}")
    
    @classmethod
    def blank(cls):
        print()
