import pandas as pd
from models import Student

def student_import_excel(file_path):
    df = pd.read_excel(file_path)

    students = []

    

