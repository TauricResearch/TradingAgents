from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserProfile, AnalysisSession


class UserProfileInline(admin.StackedInline):
    """사용자 프로필 인라인"""
    model = UserProfile
    can_delete = False
    verbose_name_plural = '프로필'
    fields = ('default_ticker', 'preferred_research_depth', 'preferred_shallow_thinker', 'preferred_deep_thinker', 'has_openai_api_key')
    readonly_fields = ('has_openai_api_key',)
    
    def has_openai_api_key(self, obj):
        return obj.has_openai_api_key()
    has_openai_api_key.boolean = True
    has_openai_api_key.short_description = 'OpenAI API 키 보유'


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """사용자 관리자"""
    inlines = (UserProfileInline,)
    list_display = ('email', 'username', 'first_name', 'last_name', 'is_staff', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('email', 'username', 'first_name', 'last_name')
    ordering = ('email',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('개인정보', {'fields': ('first_name', 'last_name', 'username')}),
        ('권한', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('중요한 날짜', {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'password1', 'password2'),
        }),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """사용자 프로필 관리자"""
    list_display = ('user', 'default_ticker', 'preferred_research_depth', 'has_openai_api_key', 'created_at')
    list_filter = ('preferred_research_depth', 'created_at')
    search_fields = ('user__email', 'user__username', 'default_ticker')
    readonly_fields = ('created_at', 'updated_at', 'has_openai_api_key')
    
    fields = (
        'user', 'default_ticker', 'preferred_research_depth',
        'preferred_shallow_thinker', 'preferred_deep_thinker',
        'has_openai_api_key', 'created_at', 'updated_at'
    )
    
    def has_openai_api_key(self, obj):
        return obj.has_openai_api_key()
    has_openai_api_key.boolean = True
    has_openai_api_key.short_description = 'OpenAI API 키 보유'


@admin.register(AnalysisSession)
class AnalysisSessionAdmin(admin.ModelAdmin):
    """분석 세션 관리자"""
    list_display = ('user', 'ticker', 'analysis_date', 'status', 'created_at', 'duration')
    list_filter = ('status', 'analysis_date', 'created_at')
    search_fields = ('user__email', 'user__username', 'ticker')
    readonly_fields = ('created_at', 'duration')
    
    fields = (
        'user', 'ticker', 'analysis_date',
        'analysts_selected', 'research_depth', 'shallow_thinker', 'deep_thinker',
        'status', 'final_report', 'error_message',
        'created_at', 'started_at', 'completed_at', 'duration'
    )
    
    def duration(self, obj):
        if obj.started_at and obj.completed_at:
            duration = obj.completed_at - obj.started_at
            return f"{int(duration.total_seconds())}초"
        return "미완료"
    duration.short_description = '소요시간' 