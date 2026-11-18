"""Deterministic numerical checks of the public exact-search implementation."""
import argparse
from fractions import Fraction
from pathlib import Path
from common import digest, now, write_json
from t3b import enumerate_tree

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',default='local_validation.json')
    args=parser.parse_args()
    cases=[(2,8,Fraction(1,2),'terminal',16,16,Fraction(2048)),
           (2,8,Fraction(1,2),'full',510,16,Fraction(2048)),
           (2,8,Fraction(0),'full',8,8,Fraction(8)),
           (4,6,Fraction(4,5),'full',5460,24,Fraction(93750))]
    checks=[]
    for b,d,m,topology,cost,floor,upper in cases:
        actual=enumerate_tree(b,d,m,'uniform',topology)
        assert actual['nonroot_pops_including_goal']==cost
        assert actual['rank_floor']==floor
        assert Fraction(actual['levin_L_exact'])==upper
        assert actual['bound_holds']
        checks.append({'branching':b,'depth':d,'mass':str(m),'topology':topology,
                       'expansions':cost,'rank_floor':floor,'L':str(upper)})
    here=Path(__file__).resolve().parent
    record={'status':'passed','validated_utc':now(),'scope':'Post-result software checks, not a new scientific run',
            'cases':checks,'source_sha256':{name:digest(here/name) for name in ['t3b.py','common.py','validate.py']}}
    write_json(args.out,record)
    print('Passed four exact search checks')

if __name__=='__main__': main()
