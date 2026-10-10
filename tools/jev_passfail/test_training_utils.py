import unittest

from training_utils import epoch_batches


class TrainingBatchTests(unittest.TestCase):
    def test_batches_cover_each_real_input_once_and_balance_ranks(self):
        size = 103
        batches = list(epoch_batches(size, world_size=8, global_batch_size=32, seed=17, epoch=3))
        actual = [index for batch, _ in batches for index in batch]
        self.assertEqual(sorted(actual), list(range(size)))
        self.assertEqual(len(actual), len(set(actual)))
        for _, per_rank in batches:
            self.assertEqual(len({len(rank_batch) for rank_batch in per_rank}), 1)
            self.assertLessEqual(sum(len(rank_batch) for rank_batch in per_rank), 32)
        self.assertEqual(sum(index == -1 for _, ranks in batches for batch in ranks for index in batch), 1)

    def test_epoch_order_is_seeded_and_changes_by_epoch(self):
        first = list(epoch_batches(65, 8, 32, seed=23, epoch=1))
        second = list(epoch_batches(65, 8, 32, seed=23, epoch=1))
        later = list(epoch_batches(65, 8, 32, seed=23, epoch=2))
        self.assertEqual(first, second)
        self.assertNotEqual(first, later)

    def test_batch_size_must_divide_across_ranks(self):
        with self.assertRaisesRegex(ValueError, "divisible"):
            list(epoch_batches(12, world_size=8, global_batch_size=10, seed=0, epoch=1))


if __name__ == "__main__":
    unittest.main()
