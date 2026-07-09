looks like it got some results. let's make sure our AI niche also includes automation, those are two great keywords. I checked out 20260708_ai-rochester_9.md and it already looks like you're getting good results. Two questions, defining our skills, and defining our cron jobs (heartbeat):
how should we start making these skills and how should we schedule their deployement?

We need our scheduled cron (heartbeat) to work something like this:
## Every 4-6 hours:
1. look for recent jobs that have been recently marked up from detailed criteria evaluations. are any promoted or high scoring enough to justify drafting preliminary resume? if so, create the resume and mark up the front-matter that an intial resume has been drafted. update next_report.md
2. look for recent jobs that have been promoted to require specific evaluation. Use the crieria files to mark up the job's front-matter with your evaluations, scores, and rationale against approaprate criteria. update next_report.md
3. look for recent reports that haven't been given preliminary evaluations/scores against their approrpiate criteria. Give best rough estimates of scores for each job according to that niche's rubric.
4. pick niche that hasn't yet been queried against today. Based on previous queries for that niche and the scores they yielded, come up with an idea to improve on one that returned decently-interesting results recently for that query. run that query and update next_report.md
5. pick another query that hasn't been run in the last few days, run it. update next_report.md Each niche should have links to each query page (same as labels in job-ferret, listed as aliases) in the front-matter so you can see what's been run and how much interest the results got from the user, if no good info is available, use prediction based on his criteria/preferences/background) 
6. any reports that have really bad average scores? evaluate what's going on, how we can improve our strategy for the niche, how we can refine or expand the niche, if we should consider eliminating the niche, and if you have any new niche ideas that might be more productive? update next_report.md
7. Any Employers (they should all be links, so we can create a page for each and it should auto-link) that have come up in several of our queries lately? make sure they have a dedicated page, use our employer-evaluation skill to see if there's any red-flags in their job listings, do some preliminary research to see if there's reason to believe they're not really hiring, or they're not a real company, or if they have terrible corporate culture, work-life-balance, etc. start working on their bio so we know how to evaluate their listings in the future. if there's none that have turned up a lot lately, then pick an existing employer page that could be more complete in it's research, and try to get it closer to complete. update next_report.md

## Every day at 8am :
look at the state of next_report.md
what queries have been run, what have we learned, what have we discovered, present a complete list of noteworthy jobs discovered, and any that are good enough to have resumes already drafted. Look into the progress that's been made, inspect the log. Draft a complete daily report.
Every day at 9am: in next_report.md are there any noteworthy jobs that haven't been completely evaluated? close any gaps before final delivery of report.
Every day at 9:30am: look at next_report.md and try to act as a detective. what was learned? what niches can be refined, expanded, promoted, demoted, etc.? what search strategies seem to be working or not working? of all the skills we are using, how might we improve each skill? 
1. Give your complete meta-breakdown as a section in next_report.md
2. rename the file to `[today's date] - Northstar Report.md` 
3. move the file into the appropriate directory (TBD) so user will see it
4. message user in discord with this file attached
5. create a new blank `next_report.md`
4. move today's northstar 