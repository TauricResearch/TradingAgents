from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from .models import User, UserProfile, AnalysisSession
from datetime import date


class UserRegistrationSerializer(serializers.ModelSerializer):
    """사용자 회원가입 시리얼라이저"""
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ('email', 'username', 'password', 'password_confirm', 'first_name', 'last_name')
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("비밀번호가 일치하지 않습니다.")
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        
        return user


class UserLoginSerializer(serializers.Serializer):
    """사용자 로그인 시리얼라이저"""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            user = authenticate(username=email, password=password)
            if not user:
                raise serializers.ValidationError('올바르지 않은 이메일 또는 비밀번호입니다.')
            if not user.is_active:
                raise serializers.ValidationError('비활성화된 계정입니다.')
            attrs['user'] = user
        else:
            raise serializers.ValidationError('이메일과 비밀번호를 모두 입력해주세요.')
        
        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    """사용자 프로필 시리얼라이저"""
    has_openai_api_key = serializers.SerializerMethodField()
    openai_api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    class Meta:
        model = UserProfile
        fields = (
            'default_ticker', 
            'preferred_research_depth',
            'preferred_shallow_thinker',
            'preferred_deep_thinker',
            'has_openai_api_key',
            'openai_api_key',
            'created_at',
            'updated_at'
        )
        read_only_fields = ('created_at', 'updated_at')
    
    def get_has_openai_api_key(self, obj):
        return obj.has_openai_api_key()
    
    def update(self, instance, validated_data):
        openai_api_key = validated_data.pop('openai_api_key', None)
        
        # OpenAI API 키 업데이트
        if openai_api_key is not None:
            instance.set_openai_api_key(openai_api_key)
        
        # 다른 필드 업데이트
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        return instance


class UserSerializer(serializers.ModelSerializer):
    """사용자 정보 시리얼라이저"""
    profile = UserProfileSerializer(read_only=True)
    
    class Meta:
        model = User
        fields = ('id', 'email', 'username', 'first_name', 'last_name', 'profile', 'date_joined')
        read_only_fields = ('id', 'email', 'date_joined')


class AnalysisSessionSerializer(serializers.ModelSerializer):
    """분석 세션 시리얼라이저"""
    user_email = serializers.CharField(source='user.email', read_only=True)
    duration = serializers.SerializerMethodField()
    
    class Meta:
        model = AnalysisSession
        fields = (
            'id', 'user_email', 'ticker', 'analysis_date',
            'analysts_selected', 'research_depth', 'shallow_thinker', 'deep_thinker',
            'status', 'final_report', 'error_message',
            'created_at', 'started_at', 'completed_at', 'duration'
        )
        read_only_fields = ('id', 'user_email', 'created_at', 'duration')
    
    def get_duration(self, obj):
        if obj.started_at and obj.completed_at:
            duration = obj.completed_at - obj.started_at
            return int(duration.total_seconds())
        return None


class CreateAnalysisSessionSerializer(serializers.ModelSerializer):
    """분석 세션 생성 시리얼라이저"""
    class Meta:
        model = AnalysisSession
        fields = (
            'ticker',
            'analysts_selected', 'research_depth',
            'shallow_thinker', 'deep_thinker'
        )
        # analysis_date는 create 시점에 자동 생성되므로 필드에서 제외

    def create(self, validated_data):
        """오늘 날짜를 추가하여 세션 생성"""
        validated_data['analysis_date'] = date.today()
        return super().create(validated_data)

    def validate_analysts_selected(self, value):
        """선택된 분석가들 검증"""
        if not isinstance(value, list) or len(value) == 0:
            raise serializers.ValidationError("최소 하나의 분석가를 선택해야 합니다.")
        
        valid_analysts = ['market', 'social', 'news', 'fundamentals']
        for analyst in value:
            if analyst not in valid_analysts:
                raise serializers.ValidationError(f"올바르지 않은 분석가: {analyst}")
        
        return value
    
    def validate_research_depth(self, value):
        """연구 깊이 검증"""
        if value not in [1, 3, 5]:
            raise serializers.ValidationError("연구 깊이는 1, 3, 5 중 하나여야 합니다.")
        return value 