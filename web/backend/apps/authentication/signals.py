from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, UserProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """사용자 생성 시 자동으로 프로필 생성"""
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """사용자 저장 시 프로필도 함께 저장"""
    if hasattr(instance, 'profile'):
        instance.profile.save() 