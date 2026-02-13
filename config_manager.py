import configparser
import os

class ConfigManager:
    def __init__(self, config_file='config.ini'):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.config.optionxform = str  # 대소문자 유지
        
        if not os.path.exists(self.config_file):
            self.create_default()
        else:
            self.load()

    def create_default(self):
        self.config['SETTINGS'] = {
            'AI_API_KEY': '',
            'KIPRIS_API_KEY': '',
            'TARGET_ITEMS': '공구, 전동 드릴',
            'SHOP_URLS': 'https://www.taobao.com, https://www.amazon.com',
            'ITEM_COUNT': '10',
            'EXCEL_FILE': 'result.xlsx',
            'COST_BASIC': '3000',
            'COST_EXCHANGE': '6000',
            'COST_RETURN': '6000',
            'COST_AGENCY': '10000',
            'PRICE_MIN': '0',   # 최소 가격 (0은 제한없음)
            'PRICE_MAX': '0',   # 최대 가격 (0은 제한없음)
        }
        self.save()

    def load(self):
        self.config.read(self.config_file, encoding='utf-8')
        if not self.config.sections() or 'SETTINGS' not in self.config:
            self.create_default()
            return

        settings = self.config['SETTINGS']
        is_modified = False
        
        # 키 대문자 변환 마이그레이션
        for key in list(settings.keys()):
            if key.islower():
                settings[key.upper()] = settings[key]
                del settings[key]
                is_modified = True
        
        # 기본값 보장
        defaults = {
            'COST_BASIC': '3000', 'COST_EXCHANGE': '6000', 
            'COST_RETURN': '6000', 'COST_AGENCY': '10000', 
            'ITEM_COUNT': '10', 'EXCEL_FILE': 'result.xlsx'
        }
        for k, v in defaults.items():
            if k not in settings:
                settings[k] = v
                is_modified = True

        if is_modified: self.save()

    def save(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            self.config.write(f)

    def get_val(self, key):
        if 'SETTINGS' not in self.config: return ''
        return self.config['SETTINGS'].get(key, '')

    def update_config(self, new_settings):
        if 'SETTINGS' not in self.config: self.config['SETTINGS'] = {}
        for key, value in new_settings.items():
            self.config['SETTINGS'][key] = str(value)
        self.save()