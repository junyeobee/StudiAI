import redis.asyncio as redis
import asyncio

async def test_redis_pubsub():
    # Redis 연결 (비동기 클라이언트 사용)
    redis_client = redis.Redis(
        host="localhost", 
        port=9091, 
        decode_responses=True
    )
    
    # 구독 설정
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("test-channel")
    
    # 별도 태스크로 메시지 발행
    asyncio.create_task(publish_message(redis_client))
    
    # 메시지 수신 (타임아웃 추가)
    try:
        async for message in pubsub.listen():
            print(f"수신된 메시지: {message}")
            if message['type'] == 'message':
                break
    except Exception as e:
        print(f"메시지 수신 중 오류: {str(e)}")
    
    # 정리
    await pubsub.unsubscribe("test-channel")
    await redis_client.close()

async def publish_message(redis_client):
    await asyncio.sleep(1)  # 구독이 설정될 시간 주기
    await redis_client.publish("test-channel", "테스트 메시지")
    print("메시지 발행 완료")

# 비동기 함수 실행을 위한 런타임 추가
if __name__ == "__main__":
    asyncio.run(test_redis_pubsub())