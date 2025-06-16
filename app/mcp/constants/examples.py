EXAMPLE_MAP: dict[str, str] = {
    # DB 생성
    "database_tool.create": (
        "필수: title\n"
        '{"payload":{"title":"학습 제목"}}\n'
    ),

    # 페이지 수정
    "page_tool.update": (
        "필수: page_id | payload.props[title,date,status,revisit],payload.content[goal_intro,goals],payload.summary[summary]\n"
        '{"payload":{"page_id":"","props":{"title":"새 제목","date":"2025-05-06T00:00:00Z","status":"진행중","revisit":true},"content":{"goal_intro":"수정된 목표 소개","goals":["새 목표1","새 목표2"]},"summary":{"summary":"마크다운 형식으로 작성 (한 라인에 하나의 요소만)\\n예시:내용...\\n예시)#내용...\\n>내용...\\n"}}}'
        "ai_summary는 수정이 아닌 추가입니다."
    ),

    # 페이지 생성
    "page_tool.create": (
        "필수: notion_db_id, plans[title,date,status,revisit,goal_intro,goals,summary]\n"
        '{"payload":{"notion_db_id":"","plans":[{"title":"학습 제목","date":"2025-05-06T00:00:00Z","status":"시작 전","revisit":false,"goal_intro":"학습 목표 소개","goals":["목표1","목표2"],"summary":"마크다운 형식으로 작성 (한 라인에 하나의 요소만)\\n예시:내용...\\n예시)#내용...\\n>내용...\\n"}]}}'
    ),

    # DB 페이지 조회
    "page_tool.list" : (
        "params.db_id 파라미터 넣을 시 특정 DB 페이지 리스트 조회\n"
        "파라미터 none: current DB의 리스트 조회"
    ),

    # DB 페이지 삭제
    "page_tool.delete" : (
        "params.page_id 파라미터 넣을 시 특정 페이지 삭제"
    ),

    # DB 페이지 조회
    "page_tool.get" : (
        "params.page_id 파라미터 넣을 시 특정 페이지 조회"
    ),
    
    # 워크스페이스 목록 조회
    "notion_settings_tool.workspaces" : (
        "파라미터 불필요: 사용 가능한 노션 워크스페이스 목록 조회"
    ),
    
    # 활성 워크스페이스 설정
    "notion_settings_tool.set_active_workspace" : (
        "필수: workspace_id\n"
        '{"payload":{"workspace_id":"워크스페이스_아이디"}}'
    ),
    
    # 최상위 페이지 목록 조회
    "notion_settings_tool.top_pages" : (
        "파라미터 불필요: 현재 워크스페이스의 최상위 페이지 목록 조회"
    ),
    
    # 최상위 페이지 설정
    "notion_settings_tool.set_top_page" : (
        "params.page_id: 최상위 페이지 id"
    ),
    
    # 현재 최상위 페이지 조회
    "notion_settings_tool.get_top_page" : (
        "파라미터 불필요: 현재 설정된 최상위 페이지 조회"
    ),
    "auth_tool.get_token" : (
        "params.provider: notion | github_webhook | notion_webhook\n"
        "토큰 발급 링크 반환"
    ),
    
    # GitHub 웹훅 생성
    "github_webhook_tool.create": (
        "필수: repo_url, learning_db_id | 선택: events\n"
        '{"payload":{"repo_url":"https://github.com/owner/repo","learning_db_id":"notion_db_id","events":["push"]}}'
    ),
    
    # GitHub 저장소 목록 조회
    "github_webhook_tool.repos": (
        "파라미터 불필요: 사용 가능한 GitHub 저장소 목록 조회"
    ),

    # 페이지 커밋 목록 조회
    "page_tool.commits": (
        "params.page_id 파라미터 넣을 시 특정 페이지의 커밋 목록 조회"
    ),

    # 페이지 커밋 내용 조회
    "page_tool.commit_sha": (
        "params.page_id, params.commit_sha 파라미터 넣을 시 특정 페이지의 특정 커밋 내용 조회"
    ),

    # 웹훅 작업 관련
    "webhook_tool.failed": (
        "params.limit (선택, 기본값: 10): 실패한 웹훅 작업 목록 조회"
    ),
    
    "webhook_tool.list": (
        "params.status (선택), params.limit (선택, 기본값: 50): 웹훅 작업 목록 조회"
    ),
    
    "webhook_tool.detail": (
        "params.operation_id 필수: 특정 웹훅 작업 상세 조회"
    ),
    "feedback_tool.send_feedback": (
        "payload.message 필수: 피드백 메시지\n"
        '{"payload":{"message":"피드백 내용입니다."}}'
    )
} 