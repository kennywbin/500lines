import sys, os, time, random

from functools import partial
from collections import namedtuple
from itertools import product

import neighbourhood as neigh
import heuristics as heur

##############
## Settings ##
##############
TIME_LIMIT = 300.0 # Time (in seconds) to run the solver
TIME_INCREMENT = 13.0 # Time (in seconds) in between heuristic measurements
DEBUG_SWITCH = False # Displays intermediate heuristic info when True
MAX_LNS_NEIGHBOURHOODS = 1000 # Maximum number of neighbours to explore in LNS


################
## Strategies ##
#################################################
## A strategy is a particular configuration
##  of neighbourhood generator (to compute
##  the next set of candidates) and heuristic
##  computation (to select the best candidate).
##

STRATEGIES = []

# Using a namedtuple is a little cleaner than dictionaries.
#  E.g., strategy['name'] versus strategy.name
Strategy = namedtuple('Strategy', ['name', 'neighbourhood', 'heuristic'])

def initialize_strategies():

    global STRATEGIES

    # Define the neighbourhoods (and parameters) we would like to use
    neighbourhoods = [
        ('Random Permutation', partial(neigh.neighbours_random, num=100)),
        ('Swapped Pairs', neigh.neighbours_swap),
        ('Large Neighbourhood Search (2)', partial(neigh.neighbours_LNS, size=2)),
        ('Large Neighbourhood Search (3)', partial(neigh.neighbours_LNS, size=3)),
        ('Idle Neighbourhood (3)', partial(neigh.neighbours_idle, size=3)),
        ('Idle Neighbourhood (4)', partial(neigh.neighbours_idle, size=4)),
        ('Idle Neighbourhood (5)', partial(neigh.neighbours_idle, size=5))
    ]

    # Define the heuristics we would like to use
    heuristics = [
        ('Hill Climbing', heur.heur_hillclimbing),
        ('Random Selection', heur.heur_random),
        ('Biased Random Selection', heur.heur_random_hillclimbing)
    ]

    # Combine every neighbourhood and heuristic strategy
    for (n, h) in product(neighbourhoods, heuristics):
        STRATEGIES.append(Strategy("%s / %s" % (n[0], h[0]), n[1], h[1]))



def solve(data):
    """Solves an instance of the flow shop scheduling problem"""

    # We initialize the strategies here to avoid cyclic import issues
    initialize_strategies()
    global STRATEGIES

    # Record the following for each strategy:
    #  improvements: The amount a solution was improved by this strategy
    #  time_spent: The amount of time spent on the strategy
    #  weights: The weights that correspond to how good a strategy is
    #  usage: The number of times we use a strategy
    strat_improvements = {strategy: 0 for strategy in STRATEGIES}
    strat_time_spent = {strategy: 0 for strategy in STRATEGIES}
    strat_weights = {strategy: 1 for strategy in STRATEGIES}
    strat_usage = {strategy: 0 for strategy in STRATEGIES}

    # Start with a random permutation of the jobs
    perm = range(len(data))
    random.shuffle(perm)

    # Keep track of the best solution
    best_make = makespan(data, perm)
    best_perm = perm
    res = best_make

    # Maintain statistics and timing for the iterations
    iteration = 0
    time_limit = time.time() + TIME_LIMIT
    time_last_switch = time.time()

    time_delta = TIME_LIMIT / 10
    checkpoint = time.time() + time_delta
    percent_complete = 10

    print "\nSolving..."

    while time.time() < time_limit:

        if time.time() > checkpoint:
            print " %d %%" % percent_complete
            percent_complete += 10
            checkpoint += time_delta

        iteration += 1

        # Heuristically choose the best strategy
        strategy = pick_strategy(STRATEGIES, strat_weights)

        old_val = res
        old_time = time.time()

        # Use the current strategy's heuristic to pick the next permutation from
        #  the set of candidates generated by the strategy's neighbourhood
        candidates = strategy.neighbourhood(data, perm)
        perm = strategy.heuristic(data, candidates)
        res = makespan(data, perm)

        # Record the statistics on how the strategy did
        strat_improvements[strategy] += res - old_val
        strat_time_spent[strategy] += time.time() - old_time
        strat_usage[strategy] += 1

        if res < best_make:
            best_make = res
            best_perm = perm[:]

        # At regular intervals, switch the weighting on the strategies available.
        #  This way, the search can dynamically shift towards strategies that have
        #  proven more effective recently.
        if time.time() > time_last_switch + TIME_INCREMENT:

            # Normalize the improvements made by the time it takes to make them
            results = sorted([(float(strat_improvements[s]) / max(0.001, strat_time_spent[s]), s)
                              for s in STRATEGIES])

            if DEBUG_SWITCH:
                print "\nComputing another switch..."
                print "Best performer: %s (%d)" % (results[0][1].name, results[0][0])
                print "Worst performer: %s (%d)" % (results[-1][1].name, results[-1][0])

            # Boost the weight for the successful strategies
            for i in range(len(STRATEGIES)):
                strat_weights[results[i][1]] += len(STRATEGIES) - i

                # Additionally boost the unused strategies to avoid starvation
                if results[i][0] == 0:
                    strat_weights[results[i][1]] += len(STRATEGIES)

            time_last_switch = time.time()

            if DEBUG_SWITCH:
                print results
                print sorted([strat_weights[STRATEGIES[i]] for i in range(len(STRATEGIES))])

            strat_improvements = {strategy: 0 for strategy in STRATEGIES}
            strat_time_spent = {strategy: 0 for strategy in STRATEGIES}


    print " %d %%\n" % percent_complete
    print "\nWent through %d iterations." % iteration

    print "\n(usage) Strategy:"
    results = sorted([(strat_weights[STRATEGIES[i]], i)
                      for i in range(len(STRATEGIES))], reverse=True)
    for (w, i) in results:
        print "(%d) \t%s" % (strat_usage[STRATEGIES[i]], STRATEGIES[i].name)

    return (best_perm, best_make)


def parse_problem(filename, k=1):
    """Parse the kth instance of a Taillard problem file

    The Taillard problem files are a standard benchmark set for the problem
    of flow shop scheduling. They can be found online at the following address:
    - http://mistic.heig-vd.ch/taillard/problemes.dir/ordonnancement.dir/ordonnancement.html"""

    print "\nParsing..."

    with open(filename, 'r') as f:
        # Identify the string that separates instances
        problem_line = '/number of jobs, number of machines, initial seed, upper bound and lower bound :/'

        # Strip spaces and newline characters from every line
        lines = map(str.strip, f.readlines())

        # We prep the first line for later
        lines[0] = '/' + lines[0]

        # We also know '/' does not appear in the files, so we can use it as
        #  a separator to find the right lines for the kth problem instance
        try:
            lines = '/'.join(lines).split(problem_line)[k].split('/')[2:]
        except IndexError:
            max_instances = len('/'.join(lines).split(problem_line)) - 1
            print "\nError: Instance must be within 1 and %d\n" % max_instances
            sys.exit(0)

        # Split every line based on spaces and convert each item to an int
        data = [map(int, line.split()) for line in lines]

    # We return the zipped data to rotate the rows and columns, making each
    #  item in data the durations of tasks for a particular job
    return zip(*data)


def pick_strategy(strategies, weights):
    # Picks a random strategy based on its weight: roulette wheel selection
    #  Rather than selecting a strategy entirely at random, we bias the
    #  random selection towards strategies that have worked well in the
    #  past (according to the weight value).
    total = sum([weights[strategy] for strategy in strategies])
    pick = random.uniform(0, total)
    count = weights[strategies[0]]

    i = 0
    while pick > count:
        count += weights[strategies[i+1]]
        i += 1

    return strategies[i]


def makespan(data, perm):
    """Computes the makespan of the provided solution

    For scheduling problems, the makespan refers to the difference between
    the earliest start time of any job and the latest completion time of
    any job. Minimizing the makespan amounts to minimizing the total time
    it takes to process all jobs from start to finish."""
    return compile_solution(data, perm)[-1][-1] + data[perm[-1]][-1]


def compile_solution(data, perm):
    """Compiles a scheduling on the machines given a permutation of jobs"""

    num_machines = len(data[0])

    # Note that using [[]] * m would be incorrect, as it would simply
    #  copy the same list m times (as opposed to creating m distinct lists).
    machine_times = [[] for _ in range(num_machines)]

    # Assign the initial job to the machines
    machine_times[0].append(0)
    for mach in range(1,num_machines):
        # Start the next task in the job when the previous finishes
        machine_times[mach].append(machine_times[mach-1][0] +
                                   data[perm[0]][mach-1])

    # Assign the remaining jobs
    for i in range(1, len(perm)):

        # The first machine never contains any idle time
        job = perm[i]
        machine_times[0].append(machine_times[0][-1] + data[perm[i-1]][0])

        # For the remaining machines, the start time is the max of when the
        #  previous task in the job completed, or when the current machine
        #  completes the task for the previous job.
        for mach in range(1, num_machines):
            machine_times[mach].append(max(machine_times[mach-1][i] + data[perm[i]][mach-1],
                                        machine_times[mach][i-1] + data[perm[i-1]][mach]))

    return machine_times



def print_solution(data, perm):
    """Prints statistics on the computed solution"""

    sol = compile_solution(data, perm)

    print "\nPermutation: %s\n" % str([i+1 for i in perm])

    print "Makespan: %d\n" % makespan(data, perm)

    row_format ="{:>15}" * 4
    print row_format.format('Machine', 'Start Time', 'Finish Time', 'Idle Time')
    for mach in range(len(data[0])):
        finish_time = sol[mach][-1] + data[perm[-1]][mach]
        idle_time = (finish_time - sol[mach][0]) - sum([job[mach] for job in data])
        print row_format.format(mach+1, sol[mach][0], finish_time, idle_time)

    results = []
    for i in range(len(data)):
        finish_time = sol[-1][i] + data[perm[i]][-1]
        idle_time = (finish_time - sol[0][i]) - sum([time for time in data[perm[i]]])
        results.append((perm[i]+1, sol[0][i], finish_time, idle_time))

    print "\n"
    print row_format.format('Job', 'Start Time', 'Finish Time', 'Idle Time')
    for r in sorted(results):
        print row_format.format(*r)

    print "\n\nNote: Idle time does not include initial or final wait time.\n"


if __name__ == '__main__':

    if len(sys.argv) == 2:
        data = parse_problem(sys.argv[1])
    elif len(sys.argv) == 3:
        data = parse_problem(sys.argv[1], int(sys.argv[2]))
    else:
        print "\nUsage: python flow.py <Taillard problem file> [<instance number>]\n"
        sys.exit(0)

    (perm, ms) = solve(data)
    print_solution(data, perm)
