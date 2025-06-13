class AppSettings:
    """
    환경 변수에 의존하지 않는 순수 상수 값들을 정의하는 클래스입니다.
    .env 파일을 읽지 않으므로 설정 충돌을 일으키지 않습니다.
    """
    # HTTP
    HTTP_TIMEOUT: float = 30.0

    # 인증
    MIN_TOKEN_LENGTH: int = 10  # Bearer 토큰 최소 길이

    # FastMCP 실행
    DEFAULT_PORT: int = 8001
    DEFAULT_HOST: str = "0.0.0.0"

    # 외부 API
    STUDYAI_API: str = "https://studiai-production.up.railway.app"

# 클래스의 인스턴스를 생성하여 import 후 바로 사용할 수 있도록 합니다.
settings = AppSettings() 