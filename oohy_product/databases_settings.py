import os

from dotenv import load_dotenv

DATABASES = {

    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('NAME'),
        'USER': os.environ.get('USER'),
        'PASSWORD': os.environ.get('PASSWORD'),
        'HOST': os.environ.get('HOST'),
        'PORT': os.environ.get('PORT'),

    }

}

load_dotenv()
