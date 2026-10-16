import assert from 'node:assert/strict';
import test from 'node:test';
import { buildNetworkGraphData, graphScopeChange, GraphTooLargeError, MAX_GRAPH_NODES, MAX_GRAPH_EDGES } from '../network-graph-data.ts';

const labels = { user: 'Пользователь', manager: 'Руководитель', admin: 'Администратор' };
const university = (id) => ({ id, name: `University ${id}`, city: 'Moscow' });
const user = (id, scope, role = 'user') => ({
  id, name: `User ${id}`, username: id, email: `${id}@example.test`, role,
  status: 'active', scope, lastLoginAt: null,
});

test('graph excludes orphan links and duplicate users, universities, and edges', () => {
  const one = user('user-1', { kind: 'universities', universityIds: ['uni-1', 'uni-1', 'deleted'] });
  const graph = buildNetworkGraphData(
    [one, one, user('admin-1', { kind: 'all' }, 'admin')],
    [university('uni-1'), university('uni-1'), university('uni-2')], labels,
  );

  assert.equal(graph.usersCount, 2);
  assert.equal(graph.universitiesCount, 2);
  assert.equal(graph.linksCount, 1);
  assert.deepEqual(graph.edges, [{ id: 'user-1::uni-1', userId: 'user-1', universityId: 'uni-1' }]);
  assert.equal(graph.nodes.find((node) => node.id === 'user-1').degree, 1);
  assert.equal(graph.nodes.find((node) => node.id === 'uni-1').degree, 1);
  assert.equal(graph.nodes.find((node) => node.id === 'admin-1').allAccess, true);
  assert.equal(graph.isolatedCount, 1);
});

test('graph node and edge order does not depend on API page order', () => {
  const users = [
    user('user-b', { kind: 'universities', universityIds: ['uni-b', 'uni-a'] }),
    user('user-a', { kind: 'universities', universityIds: ['uni-a'] }),
  ];
  const universities = [university('uni-b'), university('uni-a')];
  const first = buildNetworkGraphData(users, universities, labels);
  const reversed = buildNetworkGraphData([...users].reverse(), [...universities].reverse(), labels);

  assert.deepEqual(first, reversed);
  assert.deepEqual(first.edges.map((edge) => edge.id), [
    'user-a::uni-a', 'user-b::uni-a', 'user-b::uni-b',
  ]);
});

test('large datasets fail closed before the interactive layout can freeze', () => {
  const universities = Array.from({ length: MAX_GRAPH_NODES + 1 }, (_, i) => university(`uni-${i}`));
  assert.throws(() => buildNetworkGraphData([], universities, labels), GraphTooLargeError);

  const withinLimit = universities.slice(0, MAX_GRAPH_NODES / 2);
  const denseUsers = Array.from({ length: MAX_GRAPH_NODES / 2 }, (_, i) =>
    user(`user-${i}`, { kind: 'universities', universityIds: withinLimit.map((item) => item.id) }));
  assert.equal(denseUsers.length + withinLimit.length, MAX_GRAPH_NODES);
  assert.ok(denseUsers.length * withinLimit.length > MAX_GRAPH_EDGES);
  assert.throws(() => buildNetworkGraphData(denseUsers, withinLimit, labels), GraphTooLargeError);
});

test('scope edits preserve the freshly fetched role and other university assignments', () => {
  const current = user('user-1', { kind: 'universities', universityIds: ['uni-1', 'uni-2'] }, 'manager');
  assert.deepEqual(graphScopeChange(current, 'uni-3', 'add'), {
    role: 'manager', scope: { kind: 'universities', universityIds: ['uni-1', 'uni-2', 'uni-3'] },
  });
  assert.deepEqual(graphScopeChange(current, 'uni-1', 'remove'), {
    role: 'manager', scope: { kind: 'universities', universityIds: ['uni-2'] },
  });
  assert.throws(() => graphScopeChange(user('admin-1', { kind: 'all' }, 'admin'), 'uni-1', 'add'));
  assert.throws(() => graphScopeChange(current, 'uni-missing', 'remove'));
});
