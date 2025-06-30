FROM python:3.11
WORKDIR /AI4RELEASENOTES
COPY requirements.txt ./
RUN python -m pip install -r requirements.txt
COPY . .
CMD ["python", "get_issues_sk.py"]
EXPOSE 5000