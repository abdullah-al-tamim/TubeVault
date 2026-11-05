import {describe,it,expect} from 'vitest';
import {bytes,percent} from './utils';
describe('archive progress',()=>{it('formats large original files',()=>{expect(bytes(5*1024**3)).toBe('5.0 GB');expect(bytes(0)).toBe('0 B');});it('bounds progress and handles unknown sizes',()=>{expect(percent(5,10)).toBe(50);expect(percent(12,10)).toBe(100);expect(percent(0,0)).toBe(0);});});
