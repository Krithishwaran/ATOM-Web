import platform
import os
import sys

def print_system_info():
    print("=== System Information ===")
    print(f"Operating System: {platform.system()} {platform.release()}")
    print(f"Machine: {platform.machine()}")
    print(f"Processor: {platform.processor()}")
    print(f"Python Version: {platform.python_version()}")
    print(f"Python Executable: {sys.executable}")
    print(f"Current Working Directory: {os.getcwd()}")
    print(f"User: {os.getlogin()}")
    print("==========================")

if __name__ == "__main__":
    print_system_info()
