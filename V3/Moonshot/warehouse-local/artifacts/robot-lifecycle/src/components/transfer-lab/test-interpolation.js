import { getInterpolatedPosition } from './interpolation';
import * as assert from 'assert';
import { remainingZonePicks } from './stock-playback';

function runTests() {
  const mapNodes = [
    { id: 'node_start', x: 0, y: 0 },
    { id: 'node_a', x: 10, y: 0 },
    { id: 'node_b', x: 20, y: 0 },
    { id: 'node_c', x: 20, y: 10 },
  ];

  const robotEvents = [
    {
      start: 10,
      end: 20,
      path: ['node_a', 'node_b', 'node_c'],
      order_ids: ['order_1'],
    },
    {
      start: 30,
      end: 40,
      path: ['node_c', 'node_start'],
      order_ids: [],
    }
  ];

  // Test 1: Before any event (should use startNode)
  let result = getInterpolatedPosition(0, robotEvents, mapNodes, 'node_start');
  assert.strictEqual(result.x, 0, 'Test 1 X failed');
  assert.strictEqual(result.y, 0, 'Test 1 Y failed');
  assert.strictEqual(result.isBusy, false, 'Test 1 isBusy failed');

  // Test 2: At exactly start time of first event
  result = getInterpolatedPosition(10, robotEvents, mapNodes, 'node_start');
  assert.strictEqual(result.x, 10, 'Test 2 X failed'); // node_a.x
  assert.strictEqual(result.y, 0, 'Test 2 Y failed');
  assert.strictEqual(result.isBusy, true, 'Test 2 isBusy failed');
  assert.deepStrictEqual(result.activeOrderIds, ['order_1'], 'Test 2 orders failed');

  // Test 3: Exactly halfway through first event (should be at node_b)
  result = getInterpolatedPosition(15, robotEvents, mapNodes, 'node_start');
  assert.strictEqual(result.x, 20, 'Test 3 X failed'); // node_b.x
  assert.strictEqual(result.y, 0, 'Test 3 Y failed'); // node_b.y
  assert.strictEqual(result.isBusy, true, 'Test 3 isBusy failed');

  // Test 4: Between events (should stay at last node of first event)
  result = getInterpolatedPosition(25, robotEvents, mapNodes, 'node_start');
  assert.strictEqual(result.x, 20, 'Test 4 X failed'); // node_c.x
  assert.strictEqual(result.y, 10, 'Test 4 Y failed'); // node_c.y
  assert.strictEqual(result.isBusy, false, 'Test 4 isBusy failed');

  // Test 5: During second event (halfway)
  result = getInterpolatedPosition(35, robotEvents, mapNodes, 'node_start');
  assert.strictEqual(result.x, 10, 'Test 5 X failed'); // halfway between node_c (20) and node_start (0)
  assert.strictEqual(result.y, 5, 'Test 5 Y failed'); // halfway between node_c (10) and node_start (0)
  assert.strictEqual(result.isBusy, true, 'Test 5 isBusy failed');

  // Test 6: After all events
  result = getInterpolatedPosition(50, robotEvents, mapNodes, 'node_start');
  assert.strictEqual(result.x, 0, 'Test 6 X failed'); // node_start.x
  assert.strictEqual(result.y, 0, 'Test 6 Y failed'); // node_start.y
  assert.strictEqual(result.isBusy, false, 'Test 6 isBusy failed');

  // A picker claimed as a donor stays at its final bin while the receiver moves.
  const transferClaim = [{
    start: 30,
    end: 40,
    path: ['node_c', 'node_start'],
    order_ids: ['order_1'],
    donor_robot_id: 'picker_1',
  }];
  result = getInterpolatedPosition(35, [robotEvents[0]], mapNodes, 'node_start', transferClaim);
  assert.strictEqual(result.x, 20, 'Donor claim X failed');
  assert.strictEqual(result.y, 10, 'Donor claim Y failed');
  assert.strictEqual(result.isBusy, true, 'Donor claim busy state failed');
  assert.strictEqual(result.isDonorClaim, true, 'Donor claim role failed');
  assert.strictEqual(result.currentPath, null, 'Donor must not render receiver path');

  // Adjacent events are half-open: the next action owns their shared boundary.
  const adjacentEvents = [
    { action: 'pick', start: 0, end: 10, path: ['node_start', 'node_a'], order_ids: ['old'] },
    { action: 'transfer', start: 10, end: 20, path: ['node_a', 'node_b'], order_ids: ['new'] },
  ];
  result = getInterpolatedPosition(10, adjacentEvents, mapNodes, 'node_start');
  assert.deepStrictEqual(result.activeOrderIds, ['new'], 'Shared boundary must select the new action');
  assert.strictEqual(result.x, 10, 'Shared boundary must remain position-continuous');

  // Segment time is proportional to distance, not the number of path edges.
  const unevenPath = [{
    action: 'transfer',
    start: 0,
    end: 20,
    path: ['node_start', 'node_a', 'node_c'],
  }];
  result = getInterpolatedPosition(10, unevenPath, mapNodes, 'node_start');
  assert.ok(Math.abs(result.x - 11.4644660941) < 0.000001, 'Uneven path X must follow distance');
  assert.ok(Math.abs(result.y - 1.4644660941) < 0.000001, 'Uneven path Y must follow distance');
  result = getInterpolatedPosition(20, unevenPath, mapNodes, 'node_start');
  assert.strictEqual(result.x, 20, 'Event end must resolve to its final position');
  assert.strictEqual(result.y, 10, 'Event end continuity failed');

  const sequentialPicks = [
    { action: 'pick', start: 0, end: 45, node_id: 'node_a', path: ['node_start', 'node_a'] },
    { action: 'pick', start: 45, end: 90, node_id: 'node_b', path: ['node_a', 'node_b'] },
    { action: 'transfer', start: 90, end: 157.5, node_id: 'node_start', path: ['node_b', 'node_start'] },
  ];
  result = getInterpolatedPosition(40, sequentialPicks, mapNodes, 'node_start');
  assert.strictEqual(result.x, 10, 'Pick must stop at zone for pickup');
  result = getInterpolatedPosition(60, sequentialPicks, mapNodes, 'node_start');
  assert.ok(result.x > 10 && result.x < 20, 'Batched robot must move to next order');
  result = getInterpolatedPosition(120, sequentialPicks, mapNodes, 'node_start');
  assert.ok(result.x > 0 && result.x < 20, 'Transfer must return toward conveyor');
  result = getInterpolatedPosition(160, sequentialPicks, mapNodes, 'node_start');
  assert.strictEqual(result.x, 0, 'Completed robot remains at conveyor');

  const stockMap = { nodes: mapNodes.map(n => ({ ...n, zone_id: n.id === 'node_start' ? undefined : 'zone_a' })) };
  assert.deepStrictEqual(remainingZonePicks(stockMap, sequentialPicks, 'zone_a', 0), { total: 2, remaining: 2 });
  assert.strictEqual(remainingZonePicks(stockMap, sequentialPicks, 'zone_a', 45).remaining, 1, 'Only completed pickup disappears');
  assert.strictEqual(remainingZonePicks(stockMap, sequentialPicks, 'zone_a', 90).remaining, 0, 'Zone box disappears after final pickup');
  assert.strictEqual(remainingZonePicks(stockMap, sequentialPicks, 'zone_a', 0).remaining, 2, 'Rewind restores stock');
  console.log('All interpolation and stock playback tests passed!');
}

runTests();
