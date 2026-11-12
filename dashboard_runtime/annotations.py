"""Independent annotation commands; storage owns locking and replay receipts."""
from __future__ import annotations

import copy
import re

from .model import identifier, new_document, require, validate


def preserve_content_version(note, previous):
    if previous is not None:
        changed = any(note.get(key) != previous.get(key) for key in ('text', 'componentId', 'anchor'))
        if changed or 'contentVersion' in previous:
            note['contentVersion'] = previous.get('contentVersion', 0) + int(changed)


def validate_command(command):
    require(isinstance(command, dict), 'Annotation command must be an object')
    require(isinstance(command.get('operationId'), str) and
            re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', command['operationId']),
            'A stable operationId is required')
    identifier(command.get('annotationId'), 'annotation id')
    action = command.get('action')
    require(action in ('add', 'edit', 'delete', 'reply', 'status'), 'Unknown annotation action')
    if action in ('edit', 'delete'):
        require(type(command.get('expectedVersion')) is int and command['expectedVersion'] >= 0,
                'Provide the annotation contentVersion')
    if action == 'status':
        require(command.get('status') in ('open', 'resolved') and
                command.get('expectedStatus') in ('open', 'resolved'), 'Invalid annotation status')
    if action in ('add', 'edit', 'reply'):
        value = command.get('value')
        require(isinstance(value, dict), 'Annotation value is required')
        note = {**value, 'id': command['annotationId'], 'createdAt': 'validated'}
        if action == 'reply':
            note = {'id': command['annotationId'], 'text': value.get('text'), 'createdAt': 'validated'}
            require(isinstance(value.get('id'), str) and
                    re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', value['id']), 'Invalid reply id')
        if action != 'edit':
            require(isinstance(value.get('createdAt'), str) and 0 < len(value['createdAt']) <= 100,
                    'Creation timestamp required')
        # Reuse the canonical text/anchor validation without fetching a document.
        doc = new_document('annotation', 'Annotation')
        note['context'] = {}
        doc['manifest']['annotations'] = [note]
        validate(doc)


def apply_command(notes, command, context):
    notes = copy.deepcopy(notes)
    action, key = command['action'], command['annotationId']
    note = next((item for item in notes if item['id'] == key), None)
    if action == 'add':
        require(note is None, 'Annotation ID already exists', 'ANNOTATION_CONFLICT')
        require(len(notes) < 100, 'At most 100 annotations per document')
        value = command['value']
        note = {name: copy.deepcopy(value[name]) for name in
                ('text', 'componentId', 'anchor', 'createdAt', 'view') if name in value}
        note.setdefault('componentId', None)
        note.update(id=key, contentVersion=1, context=context)
        notes.append(note)
    else:
        require(note is not None, '批注已被删除；当前输入已保留。', 'ANNOTATION_NOT_FOUND')
        if action in ('edit', 'delete'):
            require(note.get('contentVersion', 0) == command['expectedVersion'],
                    '这条批注已更新；请重新打开，当前输入已保留。', 'ANNOTATION_CONFLICT')
        if action == 'delete':
            notes.remove(note)
        elif action == 'edit':
            note.update({name: copy.deepcopy(command['value'][name]) for name in
                         ('text', 'componentId', 'anchor') if name in command['value']})
            note['contentVersion'] = note.get('contentVersion', 0) + 1
        elif action == 'reply':
            require(note.get('status', 'open') != 'resolved', '批注已解决，请先重新打开。', 'ANNOTATION_CONFLICT')
            replies = note.setdefault('replies', [])
            require(not any(item['id'] == command['value']['id'] for item in replies),
                    'Reply ID already exists', 'ANNOTATION_CONFLICT')
            replies.append({name: command['value'][name] for name in ('id', 'text', 'createdAt')})
        elif action == 'status':
            require(note.get('status', 'open') == command['expectedStatus'],
                    '批注状态已更新，请重新打开。', 'ANNOTATION_CONFLICT')
            note['status'] = command['status']
    return notes
