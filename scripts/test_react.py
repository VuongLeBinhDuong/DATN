import sys
sys.path.append(r'd:\DATN')
sys.stdout.reconfigure(encoding='utf-8')
import json
import logging
from agent.react.agent import ReActAgent

logging.basicConfig(level=logging.INFO)

agent = ReActAgent()
question = 'Bệnh nhân suy thận độ 3 có nên uống Metformin không?'
print(f'Question: {question}')
result = agent.run_sync(question)

print('\n' + '='*60)
print('FINAL ANSWER:')
print('='*60)
print(result['answer'])

print('\n' + '='*60)
print('STEPS TAKEN:')
print('='*60)
for step in result['plan']['steps']:
    print(step)

print('\n' + '='*60)
print('SOURCES (RAG):')
print('='*60)
for source in result['sources']:
    print(f"- {source['title']} (Score: {source.get('score', 'N/A')})")
