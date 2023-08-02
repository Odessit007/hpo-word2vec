import boto3
from prefect_aws import AwsCredentials

aws_block = AwsCredentials.load('aws-credentials')
client = aws_block.get_s3_client()

from pprint import pprint
pprint(client.list_buckets())


# client = boto3.client(
#     's3',
#     region_name='us-east-1',
#     aws_access_key_id='ASIATG3QG5NYPF4UCFLA',
#     aws_secret_access_key='U/lr2jlLruyGYx9sJzt11+FPqHKAVzjcPAw+is3o',
#     aws_session_token='IQoJb3JpZ2luX2VjEEsaCXVzLWVhc3QtMSJIMEYCIQCrHaZEitztw6dJi4r0aZACvvc19IQzQ/slSmSfOpgpBwIhALZ3BZZvksZUqw0JjO0XvDA7HYROQNrAsnG/N1LMn2TkKoADCOT//////////wEQABoMMjIwODg5Mjc5MzQ0IgxB7b+e6RmfbpwiyUUq1AJVWkNTSSfoMVuATTc0DfLD5yu4YSAQlTdsQSQPCUz1MtMs3tqnQXVKgrO4JZHB4CFmuZcZu1IubCoWwcW0kRVOTzuY0ymBSucOdss/tLPg1wHep5PW8howTfQtIn0FpjB9SGOLgaVL8Z45c/K60H9QwTN8cZnJU0cObxdxbkvYwgpijprHA6u9bqIzFKLwP4zLpfsFm52ZXUgW2+pfzNcm+rI+Jg1wwtkNBJquSxRctHVDKVaD7D50HLy0UHR9pIjjPLZksSwp/X/AXYT1uk89TcAnNbUgtKGJhb0JTWycsVDbPrMeW2K7UkZsxTNGxjGp5LO9qhSoFyvZstnRnliIksYysYFl+5hcGXyp36Wio5U+sxdQBDjCpGE3i9Hw1eg41OAeMLn8lGnW85XbtAeteiav4qi5wO32qCxoER8cCpVOMI/gv+nYK8y7nIYJgSwSy8opMPiMp6YGOqYBPD1xomvFduqWz7JC2QhePoBXYMaJmQX02H1vWg+6XFqyj9nHeoAy+iIbNpgx/wfg6j2/OxI1JLuEmUresu2mtPCdiDddpEGLTmm0kZ/SIaPWJy8BjQ7L59QHW5Ix4Xw1xUSKk9ee8iqFEW1Zhu61d0xz/+ncDvQRg3+2Bi9cJBv4hhZzsaPx2NfS5TMyVbMmn1VNdWxIhMNB+dLsmtM9l91qg7EWaA=='
# )
# print(client.list_buckets())
