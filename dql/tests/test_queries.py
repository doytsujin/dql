""" Tests for queries """
from boto.exception import JSONResponseError

from . import BaseSystemTest
from ..models import TableField


class TestQueries(BaseSystemTest):

    """ System tests for queries """

    def test_create(self):
        """ CREATE statement should make a table """
        self.query(
            """
            CREATE TABLE foobar (owner STRING HASH KEY,
                                 id BINARY RANGE KEY,
                                 ts NUMBER INDEX('ts-index'))
            """)
        desc = self.engine.describe('foobar')
        self.assertEquals(desc.hash_key, TableField('owner', 'STRING', 'HASH'))
        self.assertEquals(desc.range_key, TableField('id', 'BINARY', 'RANGE'))
        self.assertItemsEqual(desc.indexes.values(),
                              [TableField('ts', 'NUMBER', 'INDEX', 'ts-index')])

    def test_create_throughput(self):
        """ CREATE statement can specify throughput """
        self.query(
            "CREATE TABLE foobar (id STRING HASH KEY) THROUGHPUT (1, 2)")
        desc = self.engine.describe('foobar')
        self.assertEquals(desc.read_throughput, 1)
        self.assertEquals(desc.write_throughput, 2)

    def test_alter_throughput(self):
        """ Can alter throughput of a table """
        self.query(
            "CREATE TABLE foobar (id STRING HASH KEY) THROUGHPUT (1, 1)")
        self.query("ALTER TABLE foobar SET THROUGHPUT (2, 2)")
        desc = self.engine.describe('foobar', refresh=True)
        self.assertEquals(desc.read_throughput, 2)
        self.assertEquals(desc.write_throughput, 2)

    def test_alter_throughput_partial(self):
        """ Can alter just read or just write throughput of a table """
        self.query(
            "CREATE TABLE foobar (id STRING HASH KEY) THROUGHPUT (1, 1)")
        self.query("ALTER TABLE foobar SET THROUGHPUT (2, 0)")
        desc = self.engine.describe('foobar', refresh=True)
        self.assertEquals(desc.read_throughput, 2)
        self.assertEquals(desc.write_throughput, 1)

    def test_create_if_not_exists(self):
        """ CREATE IF NOT EXISTS shouldn't fail if table exists """
        self.query("CREATE TABLE foobar (owner STRING HASH KEY)")
        self.query("CREATE TABLE IF NOT EXISTS foobar (owner STRING HASH KEY)")

    def test_drop(self):
        """ DROP statement should drop a table """
        self.query("CREATE TABLE foobar (id STRING HASH KEY)")
        self.query("DROP TABLE foobar")
        try:
            self.dynamo.describe_table('foobar')['Table']
        except JSONResponseError as e:
            self.assertEquals(e.status, 400)
        else:
            assert False, "Table should not exist"

    def test_drop_if_exists(self):
        """ DROP IF EXISTS shouldn't fail if no table """
        self.query("CREATE TABLE foobar (id STRING HASH KEY)")
        self.query("DROP TABLE foobar")
        self.query("DROP TABLE IF EXISTS foobar")

    def test_insert(self):
        """ INSERT statement should create items """
        table = self.make_table()
        self.query("INSERT INTO foobar (id, bar) VALUES ('a', 1), ('b', 2)")
        items = [dict(i) for i in table.scan()]
        self.assertItemsEqual(items, [{'id': 'a', 'bar': 1},
                                      {'id': 'b', 'bar': 2}])

    def test_count(self):
        """ COUNT statement counts items """
        self.make_table()
        self.query("INSERT INTO foobar (id, bar) VALUES ('a', 1), "
                   "('a', 2)")
        count = self.query("COUNT foobar WHERE id = 'a' ")
        self.assertEquals(count, 2)

    def test_count_smart_index(self):
        """ COUNT statement auto-selects correct index name """
        self.make_table(index='ts')
        self.query("INSERT INTO foobar (id, bar, ts) VALUES ('a', 1, 100), "
                   "('a', 2, 200)")
        count = self.query("COUNT foobar WHERE id = 'a' and ts < 150")
        self.assertEquals(count, 1)

    def test_delete(self):
        """ DELETE statement removes items """
        table = self.make_table(index='ts')
        self.query("INSERT INTO foobar (id, bar) VALUES ('a', 1), ('b', 2)")
        self.query("DELETE FROM foobar WHERE id = 'a' and bar = 1")
        items = [dict(i) for i in table.scan()]
        self.assertItemsEqual(items, [{'id': 'b', 'bar': 2}])

    def test_delete_in(self):
        """ DELETE Can specify KEYS IN """
        table = self.make_table(index='ts')
        self.query("INSERT INTO foobar (id, bar) VALUES ('a', 1), ('b', 2)")
        self.query("DELETE FROM foobar WHERE KEYS IN ('a', 1)")
        items = [dict(i) for i in table.scan()]
        self.assertItemsEqual(items, [{'id': 'b', 'bar': 2}])

    def test_delete_smart_index(self):
        """ DELETE statement auto-selects correct index name """
        table = self.make_table(index='ts')
        self.query("INSERT INTO foobar (id, bar, ts) VALUES ('a', 1, 100), "
                   "('a', 2, 200)")
        self.query("DELETE FROM foobar WHERE id = 'a' "
                   "and ts > 150")
        results = table.scan()
        results = [dict(r) for r in results]
        self.assertItemsEqual(results, [{'id': 'a', 'bar': 1, 'ts': 100}])

    def test_update(self):
        """ UPDATE sets attributes """
        table = self.make_table()
        self.query("INSERT INTO foobar (id, bar, baz) VALUES ('a', 1, 1), "
                   "('b', 2, 2)")
        self.query("UPDATE foobar SET baz = 3")
        items = [dict(i) for i in table.scan()]
        self.assertItemsEqual(items, [{'id': 'a', 'bar': 1, 'baz': 3},
                                      {'id': 'b', 'bar': 2, 'baz': 3}])

    def test_update_where(self):
        """ UPDATE sets attributes when clause is true """
        table = self.make_table()
        self.query("INSERT INTO foobar (id, bar, baz) VALUES ('a', 1, 1), "
                   "('b', 2, 2)")
        self.query("UPDATE foobar SET baz = 3 WHERE id = 'a'")
        items = [dict(i) for i in table.scan()]
        self.assertItemsEqual(items, [{'id': 'a', 'bar': 1, 'baz': 3},
                                      {'id': 'b', 'bar': 2, 'baz': 2}])

    def test_update_where_in(self):
        """ UPDATE sets attributes for a set of primary keys """
        table = self.make_table()
        self.query("INSERT INTO foobar (id, bar, baz) VALUES ('a', 1, 1), "
                   "('b', 2, 2)")
        self.query(
            "UPDATE foobar SET baz = 3 WHERE KEYS IN ('a', 1), ('b', 2)")
        items = [dict(i) for i in table.scan()]
        self.assertItemsEqual(items, [{'id': 'a', 'bar': 1, 'baz': 3},
                                      {'id': 'b', 'bar': 2, 'baz': 3}])

    def test_update_increment(self):
        """ UPDATE can increment attributes """
        table = self.make_table()
        self.query("INSERT INTO foobar (id, bar, baz) VALUES ('a', 1, 1), "
                   "('b', 2, 2)")
        self.query("UPDATE foobar SET baz += 2")
        self.query("UPDATE foobar SET baz -= 1")
        items = [dict(i) for i in table.scan()]
        self.assertItemsEqual(items, [{'id': 'a', 'bar': 1, 'baz': 2},
                                      {'id': 'b', 'bar': 2, 'baz': 3}])

    def test_update_delete(self):
        """ UPDATE can delete attributes """
        table = self.make_table()
        self.query("INSERT INTO foobar (id, bar, baz) VALUES ('a', 1, 1), "
                   "('b', 2, 2)")
        self.query("UPDATE foobar SET baz = NULL")
        items = [dict(i) for i in table.scan()]
        self.assertItemsEqual(items, [{'id': 'a', 'bar': 1},
                                      {'id': 'b', 'bar': 2}])

    def test_update_returns(self):
        """ UPDATE can specify what the query returns """
        self.make_table()
        self.query("INSERT INTO foobar (id, bar, baz) VALUES ('a', 1, 1), "
                   "('b', 2, 2)")
        result = self.query("UPDATE foobar SET baz = NULL RETURNS ALL NEW ")
        items = [dict(i) for i in result]
        self.assertItemsEqual(items, [{'id': 'a', 'bar': 1},
                                      {'id': 'b', 'bar': 2}])

    def test_dump(self):
        """ DUMP SCHEMA generates 'create' statements """
        self.query("CREATE TABLE test (id STRING HASH KEY, bar NUMBER RANGE "
                   "KEY, ts NUMBER INDEX('ts-index')) THROUGHPUT (2, 6)")
        original = self.engine.describe('test')
        schema = self.query("DUMP SCHEMA")
        self.query("DROP TABLE test")
        self.query(schema)
        new = self.engine.describe('test', True)
        self.assertEquals(original, new)

    def test_dump_tables(self):
        """ DUMP SCHEMA generates 'create' statements for specific tables """
        self.query("CREATE TABLE test (id STRING HASH KEY)")
        self.query("CREATE TABLE test2 (id STRING HASH KEY)")
        schema = self.query("DUMP SCHEMA test2")
        self.query("DROP TABLE test")
        self.query("DROP TABLE test2")
        self.query(schema)
        self.engine.describe('test2', True)
        try:
            self.engine.describe('test', True)
        except JSONResponseError as e:
            self.assertEquals(e.status, 400)
        else:
            assert False, "The test table should not exist"

    def test_multiple_statements(self):
        """ Engine can execute multiple queries separated by ';' """
        result = self.engine.execute("""
            CREATE TABLE test (id STRING HASH KEY);
            INSERT INTO test (id, foo) VALUES ('a', 1), ('b', 2);
            SCAN test
        """)
        scan_result = [dict(r) for r in result]
        self.assertItemsEqual(scan_result, [{'id': 'a', 'foo': 1},
                                            {'id': 'b', 'foo': 2}])


class TestSelect(BaseSystemTest):

    """ Tests for SELECT """

    def test_hash_key(self):
        """ SELECT statement filters by hash key """
        self.make_table()
        self.query("INSERT INTO foobar (id, bar) VALUES ('a', 1), ('b', 2)")
        # FIXME: I think dynamodb local has a bug related to this...
        # results = self.query("SELECT * FROM foobar WHERE id = 'a'")
        # self.assertItemsEqual(results, [{'id': 'a', 'bar': 1}])

    def test_hash_range(self):
        """ SELECT statement filters by hash and range keys """
        self.make_table()
        self.query("INSERT INTO foobar (id, bar) VALUES ('a', 1), ('b', 2)")
        results = self.query("SELECT * FROM foobar WHERE id = 'a' and bar = 1")
        results = [dict(r) for r in results]
        self.assertItemsEqual(results, [{'id': 'a', 'bar': 1}])

    def test_get(self):
        """ SELECT statement can fetch items directly """
        self.make_table()
        self.query("INSERT INTO foobar (id, bar) VALUES ('a', 1), ('b', 2)")
        results = self.query("SELECT * FROM foobar WHERE "
                             "KEYS IN ('a', 1), ('b', 2)")
        results = [dict(r) for r in results]
        self.assertItemsEqual(results, [{'id': 'a', 'bar': 1},
                                        {'id': 'b', 'bar': 2}])

    def test_reverse(self):
        """ SELECT can reverse order of results """
        self.make_table()
        self.query("INSERT INTO foobar (id, bar) VALUES ('a', 1), ('a', 2)")
        results = self.query("SELECT * FROM foobar WHERE id = 'a' ASC")
        rev_results = self.query("SELECT * FROM foobar WHERE id = 'a' DESC")
        results = [dict(r) for r in results]
        rev_results = [dict(r) for r in reversed(list(rev_results))]
        self.assertEquals(results, rev_results)

    def test_hash_index(self):
        """ SELECT statement filters by indexes """
        self.make_table(index='ts')
        self.query("INSERT INTO foobar (id, bar, ts) VALUES ('a', 1, 100), "
                   "('a', 2, 200)")
        results = self.query("SELECT * FROM foobar WHERE id = 'a' "
                             "and ts < 150 USING 'ts-index'")
        results = [dict(r) for r in results]
        self.assertItemsEqual(results, [{'id': 'a', 'bar': 1, 'ts': 100}])

    def test_smart_index(self):
        """ SELECT statement auto-selects correct index name """
        self.make_table(index='ts')
        self.query("INSERT INTO foobar (id, bar, ts) VALUES ('a', 1, 100), "
                   "('a', 2, 200)")
        results = self.query("SELECT * FROM foobar WHERE id = 'a' "
                             "and ts < 150")
        results = [dict(r) for r in results]
        self.assertItemsEqual(results, [{'id': 'a', 'bar': 1, 'ts': 100}])

    def test_limit(self):
        """ SELECT statement should be able to specify limit """
        self.make_table(index='ts')
        self.query("INSERT INTO foobar (id, bar, ts) VALUES ('a', 1, 100), "
                   "('a', 2, 200)")
        results = self.query("SELECT * FROM foobar WHERE id = 'a' LIMIT 1")
        self.assertEquals(len(list(results)), 1)

    def test_attrs(self):
        """ SELECT statement can fetch only certain attrs """
        self.make_table()
        self.query("INSERT INTO foobar (id, bar, order) VALUES "
                   "('a', 1, 'first'), ('a', 2, 'second')")
        results = self.query("SELECT order FROM foobar "
                             "WHERE id = 'a' and bar = 1")
        results = [dict(r) for r in results]
        self.assertItemsEqual(results, [{'order': 'first'}])

    def test_begins_with(self):
        """ SELECT can filter attrs that begin with a string """
        self.query("CREATE TABLE foobar (id NUMBER HASH KEY, "
                   "bar STRING RANGE KEY)")
        self.query("INSERT INTO foobar (id, bar) VALUES "
                   "(1, 'abc'), (1, 'def')")
        results = self.query("SELECT * FROM foobar "
                             "WHERE id = 1 AND bar BEGINS WITH 'a'")
        results = [dict(r) for r in results]
        self.assertItemsEqual(results, [{'id': 1, 'bar': 'abc'}])

    def test_between(self):
        """ SELECT can filter attrs that are between values"""
        self.make_table()
        self.query("INSERT INTO foobar (id, bar) VALUES "
                   "('a', 5), ('a', 10)")
        results = self.query("SELECT * FROM foobar "
                             "WHERE id = 'a' AND bar BETWEEN (1, 8)")
        results = [dict(r) for r in results]
        self.assertItemsEqual(results, [{'id': 'a', 'bar': 5}])


class TestScan(BaseSystemTest):

    """ Tests for SCAN """

    def test(self):
        """ SCAN statement gets all results in a table """
        self.make_table()
        self.query("INSERT INTO foobar (id, bar) VALUES ('a', 1), ('b', 2)")
        results = self.query("SCAN foobar")
        results = [dict(r) for r in results]
        self.assertItemsEqual(results, [{'id': 'a', 'bar': 1},
                                        {'id': 'b', 'bar': 2}])

    def test_filter(self):
        """ SCAN statement can filter results """
        self.make_table()
        self.query("INSERT INTO foobar (id, bar) VALUES ('a', 1), ('b', 2)")
        results = self.query("SCAN foobar FILTER id = 'a'")
        results = [dict(r) for r in results]
        self.assertItemsEqual(results, [{'id': 'a', 'bar': 1}])

    def test_limit(self):
        """ SCAN statement can filter results """
        self.make_table()
        self.query("INSERT INTO foobar (id, bar) VALUES ('a', 1), ('b', 2)")
        results = self.query("SCAN foobar LIMIT 1")
        self.assertEquals(len(list(results)), 1)

    def test_begins_with(self):
        """ SCAN can filter attrs that begin with a string """
        self.query("CREATE TABLE foobar (id NUMBER HASH KEY, "
                   "bar STRING RANGE KEY)")
        self.query("INSERT INTO foobar (id, bar) VALUES "
                   "(1, 'abc'), (1, 'def')")
        results = self.query("SCAN foobar "
                             "FILTER id = 1 AND bar BEGINS WITH 'a'")
        results = [dict(r) for r in results]
        self.assertItemsEqual(results, [{'id': 1, 'bar': 'abc'}])

    def test_between(self):
        """ SCAN can filter attrs that are between values"""
        self.make_table()
        self.query("INSERT INTO foobar (id, bar) VALUES "
                   "('a', 5), ('a', 10)")
        results = self.query("SCAN foobar "
                             "FILTER id = 'a' AND bar BETWEEN (1, 8)")
        results = [dict(r) for r in results]
        self.assertItemsEqual(results, [{'id': 'a', 'bar': 5}])

    def test_null(self):
        """ SCAN can filter if an attr is null """
        self.make_table()
        self.query("INSERT INTO foobar (id, bar) VALUES ('a', 5)")
        self.query("INSERT INTO foobar (id, bar, baz) VALUES ('a', 1, 1)")
        results = self.query("SCAN foobar "
                             "FILTER id = 'a' AND baz IS NULL")
        results = [dict(r) for r in results]
        self.assertItemsEqual(results, [{'id': 'a', 'bar': 5}])

    def test_not_null(self):
        """ SCAN can filter if an attr is not null """
        self.make_table()
        self.query("INSERT INTO foobar (id, bar) VALUES ('a', 5)")
        self.query("INSERT INTO foobar (id, bar, baz) VALUES ('a', 1, 1)")
        results = self.query("SCAN foobar "
                             "FILTER id = 'a' AND baz IS NOT NULL")
        results = [dict(r) for r in results]
        self.assertItemsEqual(results, [{'id': 'a', 'bar': 1, 'baz': 1}])

    def test_in(self):
        """ SCAN can filter if an attr is in a set """
        self.make_table()
        self.query("INSERT INTO foobar (id, bar) VALUES ('a', 5), ('a', 2)")
        results = self.query("SCAN foobar "
                             "FILTER id = 'a' AND bar IN (1, 3, 5)")
        results = [dict(r) for r in results]
        self.assertItemsEqual(results, [{'id': 'a', 'bar': 5}])

    def test_contains(self):
        """ SCAN can filter if a set contains an item """
        self.make_table()
        self.query("INSERT INTO foobar (id, bar, baz) VALUES "
                   "('a', 5, (1, 2, 3)), ('a', 1, (4, 5, 6))")
        results = self.query("SCAN foobar "
                             "FILTER id = 'a' AND baz CONTAINS 2")
        results = [dict(r) for r in results]
        self.assertItemsEqual(results, [{'id': 'a', 'bar': 5,
                                         'baz': set([1, 2, 3])}])

    def test_not_contains(self):
        """ SCAN can filter if a set contains an item """
        self.make_table()
        self.query("INSERT INTO foobar (id, bar, baz) VALUES "
                   "('a', 5, (1, 2, 3)), ('a', 1, (4, 5, 6))")
        results = self.query("SCAN foobar "
                             "FILTER id = 'a' AND baz NOT CONTAINS 5")
        results = [dict(r) for r in results]
        self.assertItemsEqual(results, [{'id': 'a', 'bar': 5,
                                         'baz': set([1, 2, 3])}])