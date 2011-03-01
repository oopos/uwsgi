#include "uwsgi.h"

extern struct uwsgi_server uwsgi;

int uwsgi_signal_handler(uint8_t sig) {

	struct uwsgi_signal_entry *use = NULL; 

	use = &uwsgi.shared->signal_table[sig];

	if (!uwsgi.p[use->modifier1]->signal_handler) {
		return -1;
	}	
	
	return uwsgi.p[use->modifier1]->signal_handler(sig, use->handler);
}

int uwsgi_register_signal(uint8_t sig, char *receiver, void *handler, uint8_t modifier1) {

	struct uwsgi_signal_entry *use = NULL;

	if (strlen(receiver) > 63) return -1;

	uwsgi_lock(uwsgi.signal_table_lock);

	use = &uwsgi.shared->signal_table[sig];

	strcpy(use->receiver, receiver);
	use->handler = handler;
	use->modifier1 = modifier1;
	
	uwsgi_log("registered signal %d\n", sig);

	uwsgi_unlock(uwsgi.signal_table_lock);

	return 0;
}


int uwsgi_add_file_monitor(uint8_t sig, char *filename) {

	if (strlen(filename) > (0xff-1)) {
		uwsgi_log("uwsgi_add_file_monitor: invalid filename length\n");
		return -1;
	}

	uwsgi_lock(uwsgi.fmon_table_lock);

	if (ushared->files_monitored_cnt < 64) {

		// fill the fmon table, the master will use it to add items to the event queue
		memcpy(ushared->files_monitored[ushared->files_monitored_cnt].filename, filename, strlen(filename));
                ushared->files_monitored[ushared->files_monitored_cnt].registered = 0;
		ushared->files_monitored[ushared->files_monitored_cnt].sig = sig;
	
		ushared->files_monitored_cnt++;
	}
	else {
		uwsgi_log("you can register max 64 file monitors !!!\n");
		uwsgi_unlock(uwsgi.fmon_table_lock);
		return -1;
	}

	uwsgi_unlock(uwsgi.fmon_table_lock);

	return 0;

}

int uwsgi_add_timer(uint8_t sig, int secs) {

	uwsgi_lock(uwsgi.timer_table_lock);

	if (ushared->timers_cnt < 64) {

		// fill the timer table, the master will use it to add items to the event queue
		ushared->timers[ushared->timers_cnt].value = secs;
		ushared->timers[ushared->timers_cnt].registered = 0;
		ushared->timers[ushared->timers_cnt].sig = sig;
		ushared->timers_cnt++;
	}
	else {
		uwsgi_log("you can register max 64 timers !!!\n");
		uwsgi_unlock(uwsgi.timer_table_lock);
		return -1;
	}

	uwsgi_unlock(uwsgi.timer_table_lock);

	return 0;

}

int uwsgi_signal_add_rb_timer(uint8_t sig, int secs, int iterations) {

        uwsgi_lock(uwsgi.rb_timer_table_lock);

        if (ushared->rb_timers_cnt < 64) {

                // fill the timer table, the master will use it to add items to the event queue
                ushared->rb_timers[ushared->rb_timers_cnt].value = secs;
                ushared->rb_timers[ushared->rb_timers_cnt].registered = 0;
                ushared->rb_timers[ushared->rb_timers_cnt].iterations = iterations;
                ushared->rb_timers[ushared->rb_timers_cnt].iterations_done = 0;
                ushared->rb_timers[ushared->rb_timers_cnt].sig = sig;
                ushared->rb_timers_cnt++;
        }
        else {
                uwsgi_log("you can register max 64 rb_timers !!!\n");
                uwsgi_unlock(uwsgi.rb_timer_table_lock);
                return -1;
        }

        uwsgi_unlock(uwsgi.rb_timer_table_lock);

        return 0;

}



void uwsgi_route_signal(uint8_t sig) {

	struct uwsgi_signal_entry *use = &ushared->signal_table[sig];
	// send to first available worker
	if (use->receiver[0] == 0 || !strcmp(use->receiver, "worker") || !strcmp(use->receiver, "worker0")) {
		if (write(ushared->worker_signal_pipe[0], &sig, 1) != 1) {
			uwsgi_error("write()");
			uwsgi_log("could not deliver signal %d to workers pool\n", sig);
		}
	}
	// send to all workers
	else if (!strcmp(use->receiver, "workers")) {
		if (write(ushared->worker_signal_pipe[0], &sig, 1) != 1) {
			uwsgi_error("write()");
			uwsgi_log("could not deliver signal %d to workers pool\n", sig);
		}
	}
	// route to subscribed
	else if (!strcmp(use->receiver, "subscribed")) {
	}
	else {
		// unregistered signal, sending it to all the workers
		uwsgi_log("^^^ ROUTING UNREGISTERED SIGNAL ^^^\n");
		if (write(ushared->worker_signal_pipe[0], &sig, 1) != 1) {
                        uwsgi_error("write()");
                        uwsgi_log("could not deliver signal %d to workers pool\n", sig);
                }

	}
}