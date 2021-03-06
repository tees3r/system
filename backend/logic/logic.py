import logging
import threading
import time
import queue

from backend.components.elements.element import Element
from backend.components.elements.element import Input_element, Output_element, Blind
from backend.components.modules.module import Output_module

from backend.components.elements.clock import clock

from backend.components.relations.dependancy import Dependancy
from backend.components.relations.regulation import Regulation

from backend.misc.sys_types import mt, et, regt, task_stat


class Logic_manager(threading.Thread):

    def __init__(self, group=None, target=None, name=None, args=(), kwargs=None, verbose=None):
        threading.Thread.__init__(self, group=None, target=None, name='LOGIC')
                 
        self._comunication_out_buffer = args[0]
        self._comunication_in_buffer = args[1]
        self._client_priority = 5
        self.logger = logging.getLogger('LOGIC')
        self.tasks = queue.Queue()

        self._setup()

    def _setup(self, ):

        for blind in Blind.items.values(): # pair blinds so two motors of the same blinds never turn on both. It would cause shortcut!
            other_blind_id  =   blind.other_blind
            blind.other_blind = Blind.items[other_blind_id]
  
    def _check_com_buffer_and_set_desired_values(self, ):
        """Checks if there are any commands from client. If so sets corresponding output element desired value"""

        def process_msg(msg):
            msg = msg.split(',')
            type = msg[0][0]
            id = int(msg[0][1:])
            val = int(msg[1])
            return type, id, val

        while not self._comunication_out_buffer.empty():
            msg = self._comunication_out_buffer.get()             
            type, id, value = process_msg(msg)
            if type == 'e':
                set_flag = False
                if value > 0:
                    set_flag = True
                Output_element.items[id].desired_value = (value, self._client_priority, set_flag) # Client has low priority. 
                self.logger.debug('Set desired value el: %s val: %s', id, value)
            elif type == 'r':
                Regulation.items[id].set_point = value
                self._comunication_in_buffer.put(msg) # Ack that regulation was set
            self.logger.debug(Output_element.elements_str())

    def _check_elements_values_and_notify(self, ):
        """Check elements new value flags which are set by modbus.
        If there are new values notify interested components and put message to communication thread"""
        clock.evaluate_time()
        for element in Element.items.values():
            if element.new_val_flag:
                self.logger.debug(element) 
                element.new_val_flag = False
                element.notify_objects() # powiadamia zainteresowane obiekty
                if element.type in (et.pir, et.rs, et.switch, et.heater, et.blind):
                    msg = 'e' + str(element.id) + ',' + str(element.value) + ',' + 's'
                else:
                    msg = 'e' + str(element.id) + ',' + str(element.value)                   
                self._comunication_in_buffer.put(msg)

    def _run_relations(self, ):
        """Runs dependancies and regulations"""

        for dep in Dependancy.items.values():
            dep.run() 

        for reg in Regulation.items.values():
            reg.run()

    def _generate_new_tasks(self,):
        """Generates queue with modules which have elements with changed value"""
        modules_to_notify = set()
        for out_element in Output_element.items.values():
            if out_element.value != out_element.desired_value:
                modules_to_notify.add(Output_module.items[out_element.module_id])

        while modules_to_notify:
            self.tasks.put(modules_to_notify.pop())

    def run(self, ):
        """Main logic loop"""
        self.logger.info('Thread {} start'. format(self.name))
        while True:            
            time.sleep(0.1)
            self._check_com_buffer_and_set_desired_values()
            self._check_elements_values_and_notify()
            self._run_relations()
            self._generate_new_tasks()


if __name__ == "__main__":
    from backend.objects_loader import objects_loader
    objects_loader()
    com_out_buffer = queue.Queue()
    com_in_buffer = queue.Queue()
    logic = Logic_manager(args=(com_out_buffer, com_in_buffer,))
    logic.logger.disabled = False
    logic.logger.setLevel("DEBUG")

    Dependancy.items[1].conditions[0].notify(0)

    while True:
        logic.run()

