import * as assert from 'assert';
import { formatApiError } from './api-error';

assert.strictEqual(
  formatApiError({ detail: { code: 'INVALID_ROW', path: ['rows', 2, 'sku'], message: 'SKU is unknown' } }),
  'INVALID_ROW · rows.2.sku: SKU is unknown'
);
assert.strictEqual(
  formatApiError({ detail: { message: 'Import failed', errors: [{ code: 'MISSING', field: 'order_id', message: 'Required' }] } }),
  'Import failed · MISSING · order_id: Required'
);
assert.strictEqual(formatApiError({ detail: 'Snapshot expired' }), 'Snapshot expired');

console.log('All API error formatter tests passed!');