import os

# Specify the root directory of your project
root_dir = "/"

# Iterate through all files and subdirectories
for root, dirs, files in os.walk(root_dir):
    for file in files:
        if file.endswith(".py"):
            file_path = os.path.join(root, file)
            with open(file_path, 'rb') as f:
                content = f.read()
                if b'\x00' in content:
                    print(f"Null byte found in file: {file_path}")
