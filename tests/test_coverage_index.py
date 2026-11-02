# SPDX-License-Identifier: GPL-3.0-only
import random,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from gpx_core import Point
from resilient_alignment import edge_covered,CoverageIndex

class CoverageIndexTests(unittest.TestCase):
    def test_same_union_decision_with_overlaps_gaps_and_boundary_tolerance(self):
        rng=random.Random(517)
        rectangles=[(6+i*.01,50+j*.01,6+(i+1)*.01,50+(j+1)*.01)
                    for i in range(20) for j in range(15) if rng.random()>.2]
        index=CoverageIndex(rectangles)
        for _ in range(1500):
            p=Point(50+rng.random()*.15,6+rng.random()*.2)
            q=Point(p.lat+rng.uniform(-.025,.025),p.lon+rng.uniform(-.025,.025))
            self.assertEqual(edge_covered(p,q,index),edge_covered(p,q,rectangles))
        for delta in (-1.01e-7,-1e-7,0,1e-7,1.01e-7):
            p=Point(50+delta,6);q=Point(50+delta,6.1)
            self.assertEqual(edge_covered(p,q,index),edge_covered(p,q,rectangles))
        self.assertLess(len(list(index.candidates(Point(50.05,6.05),Point(50.051,6.051)))),len(rectangles)//4)

    def test_large_rectangles_and_long_edges_have_bounded_index_work(self):
        rectangles=[(-180,-90,180,90),(6,50,6.01,50.01)]
        index=CoverageIndex(rectangles)
        self.assertLess(len(index.cells),20)
        self.assertTrue(edge_covered(Point(-80,-170),Point(80,170),index))

if __name__=='__main__':unittest.main()
