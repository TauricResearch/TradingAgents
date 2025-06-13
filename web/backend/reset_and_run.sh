# #!/bin/bash

# echo "🚀 Django 서버 시작 - 데이터베이스 초기화"

# # Django 설정 모듈 환경 변수 설정
# export DJANGO_SETTINGS_MODULE=tradingagents_web.settings

# # 1. 데이터베이스 초기화
# echo "🔄 데이터베이스 초기화 중..."
# docker exec -i tradingagents_mysql mysql -u root -ppassword -e "
# DROP DATABASE IF EXISTS tradingagents_db;
# CREATE DATABASE tradingagents_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
# "

# # 2. 마이그레이션
# echo "🔄 마이그레이션 중..."
# python manage.py makemigrations authentication
# python manage.py makemigrations
# python manage.py migrate

# # 3. 관리자 계정 생성
# echo "🔄 관리자 계정 생성 중..."
# python manage.py shell -c "
# from django.contrib.auth import get_user_model;
# User = get_user_model();
# if not User.objects.filter(email='admin@example.com').exists():
#     User.objects.create_superuser('admin@example.com', 'admin', 'admin123!');
#     print('✅ 관리자: admin@example.com / admin123!');
# "

# 4. 서버 시작 (환경 변수와 함께)
echo "🎉 서버 시작!"
daphne -b 0.0.0.0 -p 8000 tradingagents_web.asgi:application