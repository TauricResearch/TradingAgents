#!/bin/bash

# TradingAgents Docker 관리 스크립트
# 사용법: ./scripts/docker-commands.sh [command]

case "$1" in
    "start")
        echo "🚀 MySQL과 Redis 컨테이너를 시작합니다..."
        docker-compose up -d mysql redis
        echo "✅ 컨테이너가 시작되었습니다."
        docker-compose ps
        ;;
    
    "start-all")
        echo "🚀 모든 서비스(MySQL, Redis, phpMyAdmin)를 시작합니다..."
        docker-compose up -d
        echo "✅ 모든 컨테이너가 시작되었습니다."
        docker-compose ps
        ;;
    
    "stop")
        echo "🛑 모든 컨테이너를 중지합니다..."
        docker-compose down
        echo "✅ 컨테이너가 중지되었습니다."
        ;;
    
    "restart")
        echo "🔄 컨테이너를 재시작합니다..."
        docker-compose restart mysql redis
        echo "✅ 컨테이너가 재시작되었습니다."
        ;;
    
    "logs")
        echo "📋 컨테이너 로그를 확인합니다..."
        if [ -n "$2" ]; then
            docker-compose logs -f "$2"
        else
            docker-compose logs -f
        fi
        ;;
    
    "status")
        echo "📊 컨테이너 상태를 확인합니다..."
        docker-compose ps
        echo ""
        echo "🔍 포트 정보:"
        docker port tradingagents_mysql 2>/dev/null || echo "MySQL 컨테이너가 실행 중이지 않습니다."
        docker port tradingagents_redis 2>/dev/null || echo "Redis 컨테이너가 실행 중이지 않습니다."
        ;;
    
    "clean")
        echo "🧹 사용하지 않는 Docker 리소스를 정리합니다..."
        docker system prune -f
        echo "✅ 정리가 완료되었습니다."
        ;;
    
    "reset")
        echo "⚠️  경고: 모든 데이터가 삭제됩니다!"
        read -p "정말로 데이터베이스를 초기화하시겠습니까? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "🗑️  볼륨과 함께 컨테이너를 삭제합니다..."
            docker-compose down -v
            echo "🚀 새로운 컨테이너를 시작합니다..."
            docker-compose up -d mysql redis
            echo "✅ 데이터베이스가 초기화되었습니다."
        else
            echo "❌ 취소되었습니다."
        fi
        ;;
    
    "mysql")
        echo "🔗 MySQL 컨테이너에 연결합니다..."
        docker-compose exec mysql mysql -u root -p tradingagents_web
        ;;
    
    "redis")
        echo "🔗 Redis 컨테이너에 연결합니다..."
        docker-compose exec redis redis-cli
        ;;
    
    *)
        echo "🐳 TradingAgents Docker 관리 스크립트"
        echo ""
        echo "사용법: $0 [command]"
        echo ""
        echo "명령어:"
        echo "  start      - MySQL과 Redis 컨테이너 시작"
        echo "  start-all  - 모든 서비스 시작 (phpMyAdmin 포함)"
        echo "  stop       - 모든 컨테이너 중지"
        echo "  restart    - MySQL과 Redis 재시작"
        echo "  logs       - 컨테이너 로그 확인 (logs [service_name])"
        echo "  status     - 컨테이너 상태 확인"
        echo "  clean      - 사용하지 않는 Docker 리소스 정리"
        echo "  reset      - 데이터베이스 초기화 (주의: 모든 데이터 삭제)"
        echo "  mysql      - MySQL 컨테이너에 직접 연결"
        echo "  redis      - Redis 컨테이너에 직접 연결"
        echo ""
        echo "예시:"
        echo "  $0 start"
        echo "  $0 logs mysql"
        echo "  $0 status"
        ;;
esac 