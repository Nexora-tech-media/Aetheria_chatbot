import React from 'react'
import './style.css'
import { BiSupport } from "react-icons/bi";
import { FaPaperPlane } from "react-icons/fa";
import { useState } from 'react';
import { IoClose } from "react-icons/io5";

const App = () => {
  const [isActive, setIsActive] = useState(false);

  const handleToggle = () => {
    setIsActive(!isActive);
  };

  return (
    <div className='overflow-hidden absolute bottom-4 right-4 flex flex-col items-end font-primary'>
      <div className={`${isActive ? 'opacity-full -right-full' : 'opacity-0 translate-x-100'} flex flex-col transition-all duration-500 ease-in-out bg-neutral-200 h-100 w-80 rounded-3xl shadow-md`}>
        <header className='flex h-fit items-center gap-4 p-2 rounded-t-3xl font-primary'>
          <h1 className='bg-primary-100 py-2 px-4 rounded-full text-l'>A</h1>
          <h1 className='font-bold text-md'>Aetheria Chatbot</h1>

          <button 
          onClick={handleToggle}
          className='ml-auto mr-3 text-2xl'>
            <IoClose />
          </button>
        </header>

        <div className='bg-neutral-100 h-9/10'>Response</div>

        <div className='flex p-4 mt-auto gap-4'>
          <input 
          type="text"
          placeholder='Ask me anything...'
          className='w-full text-xl border-2 border-black rounded-2xl p-2'/>
          <button className='text-black hover:text-primary-600 transition-colors duration-150 ease-in'>
            <FaPaperPlane />
          </button>
        </div>
      </div>

      <button
      onClick={handleToggle}
      className='text-2xl text-black bg-primary p-2 mt-5 rounded-full hover:scale sticky bottom-2'>
        <BiSupport />
      </button>
    </div>
  );
};

export default App;