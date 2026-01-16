from django.contrib import admin
from .models import Account, UserImage
from django.contrib.auth.admin import UserAdmin

class UserImageInline(admin.TabularInline):
    model = UserImage
    extra = 3  # Hiển thị sẵn 3 ô trống để Admin upload ảnh ngay lập tức
    max_num = 10 # Giới hạn tối đa nếu muốn

class AccountAdmin(UserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'username', 'last_login', 'is_active')
    list_display_links = ('email', 'first_name', 'last_name')
    readonly_fields = ('last_login', 'date_joined')

    filter_horizontal = ()
    list_filter = ()
    fieldsets = ()

    ordering = ('-date_joined',)

    inlines = [UserImageInline] # Nhúng phần upload ảnh vào trang Account

admin.site.register(Account, AccountAdmin)

