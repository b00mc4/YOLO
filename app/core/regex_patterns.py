import re

_THAI_PLATE_PATTERN = re.compile(r"^[ก-ฮะ-์เ-ไ0-9\s]+$")
_NO_EMOJI_REGEX = re.compile(r"^[\u0E00-\u0E7F\x20-\x7E]+$")
_THAI_ENG_PATTERN = re.compile(r"^[\u0020-\u007E\u0E00-\u0E7F]+$")
