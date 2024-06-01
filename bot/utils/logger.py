import sys
from loguru import logger

logger.remove()
logger.add(sink=sys.stdout, format="<white>{time:YYYY-MM-DD HH:mm:ss}</white>"
                                   " | <level>{level: <5}</level>"
                                   " | <cyan><b>{line: <3}</b></cyan>"
                                   " - <white><b>{extra[session_name]}{message}</b></white>", level="INFO")

logger = logger.bind(session_name="")
logger = logger.opt(colors=True)
